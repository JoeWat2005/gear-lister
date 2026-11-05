"""Create eBay auctions / fixed-price listings from items.csv.

eBay has no public "draft" API, so this script has three modes:

  python list_ebay.py                                # VERIFY only: eBay checks every item, lists nothing
  python list_ebay.py --schedule 2026-11-07T19:00:00  # list now but start at that UK time
                                                      #   (shows under Seller Hub > Scheduled, editable until then)
  python list_ebay.py --go                            # list immediately
  python list_ebay.py --sku ITEM-003                  # only this sku (repeatable)
"""
import argparse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from gearlister import state
from gearlister.config import EBAY_ENV, ITEMS_CSV
from gearlister.ebay import EbayError, EbayTrading
from gearlister.items import load_items


def to_utc(s: str) -> str:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("Europe/London"))
    dt = dt.astimezone(timezone.utc)
    if dt <= datetime.now(timezone.utc):
        raise SystemExit("--schedule must be in the future")
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--go", action="store_true", help="actually list the items now")
    g.add_argument("--schedule", help="list now, go live at this time (UK), e.g. 2026-11-07T19:00:00")
    ap.add_argument("--sku", action="append")
    ap.add_argument("--force", action="store_true", help="re-list even if results.csv says done")
    a = ap.parse_args()

    items = [i for i in load_items(ITEMS_CSV, a.sku) if i.list_on_ebay]
    if not items:
        raise SystemExit("No items with list_on_ebay=yes and a title in items.csv")
    schedule = to_utc(a.schedule) if a.schedule else None
    live = a.go or bool(schedule)
    tr = EbayTrading()
    done = state.load()
    mode = "LISTING" if a.go else ("SCHEDULING" if schedule else "VERIFY ONLY")
    print(f"eBay {EBAY_ENV.upper()} - {mode} - {len(items)} item(s)")
    ok = fail = skip = 0
    for item in items:
        if live and not a.force and (item.sku, "ebay") in done:
            print(f"- {item.sku}: already listed ({done[(item.sku, 'ebay')]['url']}), skipping")
            skip += 1
            continue
        try:
            if live:
                root = tr.add_item(item, schedule)
                iid = tr.item_id(root)
                url = tr.item_url(iid)
                status = "scheduled" if schedule else "created"
                state.record(item.sku, "ebay", status, iid, url, tr.fees(root))
                print(f"+ {item.sku}: {status} item {iid} {url}  fees: {tr.fees(root)}")
            else:
                root = tr.verify_add_item(item, schedule)
                print(f"+ {item.sku}: OK  fees: {tr.fees(root)}")
            if root.get("warnings"):
                print(f"    warnings: {root.get('warnings')}")
            ok += 1
        except EbayError as e:
            if live:
                state.record(item.sku, "ebay", "error", note=str(e))
            print(f"x {item.sku}: {e}")
            fail += 1
    print(f"\nDone. ok={ok} failed={fail} skipped={skip}.")
    if not live:
        print("Nothing was listed. Re-run with --schedule <time> or --go when the checks pass.")
    else:
        print("Log: out/results.csv. Manage at https://www.ebay.co.uk/sh/lst/active (or /scheduled)")


if __name__ == "__main__":
    main()
