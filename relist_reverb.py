"""Relist your ended Reverb listings (and publish the drafts) at the eBay Buy It Now price.

  python relist_reverb.py                      # preview: what would go live, and at what price
  python relist_reverb.py --apply              # do it, slowly: one listing every 45-75 seconds
  python relist_reverb.py --apply --sku RV-102135548
  python relist_reverb.py --apply --delay 20   # shorter base gap between listings, in seconds

Price = the live eBay Buy It Now price for that sku. Items with no eBay Buy It Now keep their
current Reverb price. Anything that has sold on eBay is skipped, as are rows with
list_on_reverb=no in items.csv. Live listings are left live (only their price is corrected).

The gap between listings is deliberate. On 30 Oct about 30 API edits in 16 seconds got the
account flagged by Reverb's automated checks. The run stops at the first "under review" refusal.
"""
import argparse
import csv
import random
import time
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from ebay_status import fetch, row_for, sku_map
from gearlister import state
from gearlister.config import ITEMS_CSV, REVERB_CURRENCY
from gearlister.ebay import EbayTrading
from gearlister.reverb import Reverb, ReverbError


def money(v) -> Decimal | None:
    """'1,295.00' / 1295.0 -> Decimal('1295.00'); blank or zero -> None."""
    v = str(v or "").strip().replace("£", "").replace(",", "")
    try:
        d = Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if v else None
    except ArithmeticError:
        return None
    return d or None


def reverb_id(sku: str, done: dict) -> str | None:
    if sku.startswith("RV-") and sku[3:].isdigit():
        return sku[3:]
    row = done.get((sku, "reverb"))
    return row["id"] if row and row.get("id") else None


def say(msg: str):
    print(msg, flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="actually relist (default is a preview)")
    ap.add_argument("--sku", action="append", help="only this sku (repeatable)")
    ap.add_argument("--delay", type=float, default=45,
                    help="base seconds between listings; 0-30 s of random jitter is added (default 45)")
    a = ap.parse_args()

    done = state.load()
    with open(ITEMS_CSV, newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("title") or "").strip()]

    # eBay: live Buy It Now prices, and anything already sold
    tr = EbayTrading()
    ebay_skus = sku_map()
    now = datetime.now(timezone.utc)
    ebay_active = {r["sku"]: r for r in (row_for(i, ebay_skus, now) for i in fetch(tr, "ActiveList")) if r["sku"]}
    ebay_sold = {r["sku"] for r in (row_for(i, ebay_skus, now) for i in fetch(tr, "SoldList")) if r["sku"]}

    # Reverb: one bulk read of every listing (state + price), not one request per item
    rv = Reverb()
    reverb = {str(l.get("id")): l for l in rv.my_listings("all")}

    plan, skipped = [], []
    for r in rows:
        sku = (r.get("sku") or "").strip()
        if a.sku and sku not in a.sku:
            continue
        if (r.get("list_on_reverb") or "").strip().lower() in ("no", "n", "false", "0"):
            skipped.append((sku, "list_on_reverb=no"))
            continue
        lid = reverb_id(sku, done)
        l = reverb.get(lid or "")
        if not l:
            skipped.append((sku, "no Reverb listing found"))
            continue
        st = (l.get("state") or {}).get("slug", "")
        cur = money((l.get("price") or {}).get("amount"))
        title = (l.get("title") or "")[:48]
        if sku in ebay_sold:
            skipped.append((sku, "SOLD on eBay" + (" - but LIVE on Reverb, end it there!" if st == "live" else "")))
            continue
        e = ebay_active.get(sku)
        bin_ = money(e["buy_it_now_gbp"]) if e else None
        new = bin_ or cur
        if new is None:
            skipped.append((sku, "no price on Reverb or eBay"))
            continue
        if st in ("ended", "draft"):
            plan.append((sku, lid, st, title, cur, new, "publish" if st == "draft" else "relist", bool(bin_)))
        elif st == "live" and new != cur:
            plan.append((sku, lid, st, title, cur, new, "price", bool(bin_)))
        else:
            skipped.append((sku, f"already {st}" + ("" if new == cur else f" (price {cur}, eBay BIN {new})")))

    say(f"{'sku':<14} {'now':<6} {'action':<8} {'title':<48} {'Reverb':>9} -> {'new':>9}")
    for sku, lid, st, title, cur, new, action, from_bin in plan:
        tag = "" if from_bin else "  (no eBay BIN, keeps Reverb price)"
        say(f"{sku:<14} {st:<6} {action:<8} {title:<48} {cur or 0:>9} -> {new:>9}{tag}")
    for sku, why in skipped:
        say(f"- {sku}: {why}")
    say(f"\n{len(plan)} to do, {len(skipped)} skipped.")
    if not plan:
        return
    if not a.apply:
        mins = len(plan) * (a.delay + 15) / 60
        say(f"Preview only. Re-run with --apply (takes about {mins:.0f} min at --delay {a.delay:g}).")
        return

    ok = 0
    for n, (sku, lid, st, title, cur, new, action, _) in enumerate(plan):
        if n:
            time.sleep(a.delay + random.uniform(0, 30))
        body: dict = {} if action == "price" else {"publish": True}
        if new != cur:
            body["price"] = {"amount": str(new), "currency": REVERB_CURRENCY}
        try:
            rv.put(f"/listings/{lid}", body)
            after = rv.get(f"/listings/{lid}")
        except ReverbError as e:
            state.record(sku, "reverb", "error", lid, "", f"{action}: {e}")
            say(f"x {sku}: {e}")
            if "under review" in str(e).lower():
                say("Reverb says the account is under review. Stopping here.")
                break
            continue
        st2 = (after.get("state") or {}).get("slug", "?")
        price2 = (after.get("price") or {}).get("amount", "?")
        url = rv.listing_url(after)
        state.record(sku, "reverb", "relisted" if action != "price" else "price_updated", lid, url,
                     f"{st} -> {st2} at {price2}")
        say(f"+ {sku}: {st} -> {st2} at {price2}  {url}")
        ok += st2 == "live" or action == "price"
    say(f"\nDone: {ok}/{len(plan)} live at the new price. Log: out/results.csv")


if __name__ == "__main__":
    main()
