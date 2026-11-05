"""Push price changes from items.csv to your Reverb listings.

  python update_reverb_prices.py            # preview: shows old -> new for every row that differs
  python update_reverb_prices.py --apply    # actually update Reverb
  python update_reverb_prices.py --apply --sku RV-102049660
  python update_reverb_prices.py --percent -10 --apply   # ignore the csv, change every price by -10%
  python update_reverb_prices.py --from-bin --apply      # use the eBay buy_it_now_gbp column as the Reverb price
                                                         # (rows with an empty buy_it_now_gbp are left alone)

Only rows whose sku is a Reverb listing (RV-<id>, or logged in out/results.csv) are touched.
Drafts and ended listings are updated too unless you pass --live-only.
"""
import argparse
import csv
from decimal import ROUND_HALF_UP, Decimal

from gearlister import state
from gearlister.config import ITEMS_CSV, REVERB_CURRENCY
from gearlister.reverb import Reverb, ReverbError


def reverb_id(sku: str, done: dict) -> str | None:
    if sku.startswith("RV-") and sku[3:].isdigit():
        return sku[3:]
    row = done.get((sku, "reverb"))
    return row["id"] if row and row.get("id") else None


def money(v: str) -> Decimal | None:
    v = (v or "").strip().replace("£", "").replace(",", "")
    try:
        return Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if v else None
    except ArithmeticError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--sku", action="append")
    ap.add_argument("--live-only", action="store_true")
    ap.add_argument("--percent", type=Decimal, help="change every price by this %% instead of using the csv")
    ap.add_argument("--from-bin", action="store_true",
                    help="use buy_it_now_gbp (the eBay Buy It Now price) instead of price_gbp")
    a = ap.parse_args()
    if a.percent is not None and a.from_bin:
        ap.error("--percent and --from-bin cannot be combined")

    rv = Reverb()
    done = state.load()
    with open(ITEMS_CSV, newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("title") or "").strip()]

    changes, same, skipped = [], 0, 0
    for r in rows:
        sku = (r.get("sku") or "").strip()
        if a.sku and sku not in a.sku:
            continue
        lid = reverb_id(sku, done)
        if not lid:
            skipped += 1
            continue
        try:
            live = rv.get(f"/listings/{lid}")
        except ReverbError as e:
            print(f"x {sku}: {e}")
            continue
        st = (live.get("state") or {}).get("slug", "")
        if a.live_only and st != "live":
            skipped += 1
            continue
        current = money((live.get("price") or {}).get("amount", ""))
        if a.percent is not None:
            new = (current * (1 + a.percent / 100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        elif a.from_bin:
            new = money(r.get("buy_it_now_gbp"))
        else:
            new = money(r.get("price_gbp"))
        if new is None or current is None or new == current:
            same += 1
            continue
        changes.append((sku, lid, st, live.get("title", "")[:50], current, new))

    if not changes:
        print(f"No price changes found. unchanged={same} skipped={skipped}")
        return
    print(f"{'sku':<14} {'state':<6} {'title':<50} {'current':>9} -> {'new':>9}")
    for sku, lid, st, title, cur, new in changes:
        print(f"{sku:<14} {st:<6} {title:<50} {cur:>9} -> {new:>9}")
    print(f"\n{len(changes)} change(s), unchanged={same}, skipped={skipped}")

    if not a.apply:
        print("Preview only. Re-run with --apply to push these to Reverb.")
        return
    ok = 0
    for sku, lid, st, title, cur, new in changes:
        try:
            rv.put(f"/listings/{lid}", {"price": {"amount": str(new), "currency": REVERB_CURRENCY}})
            state.record(sku, "reverb", "price_updated", lid, "", f"{cur} -> {new}")
            print(f"+ {sku}: {cur} -> {new}")
            ok += 1
        except ReverbError as e:
            print(f"x {sku}: {e}")
    print(f"\nUpdated {ok}/{len(changes)} on Reverb.")


if __name__ == "__main__":
    main()
