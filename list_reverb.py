"""Create Reverb listings from items.csv.

  python list_reverb.py                 # create DRAFTS (not visible to buyers)
  python list_reverb.py --dry-run       # print the payloads, send nothing
  python list_reverb.py --publish       # create and publish immediately
  python list_reverb.py --sku ITEM-003  # only this sku (repeatable)
"""
import argparse
import json

from gearlister import state
from gearlister.config import ITEMS_CSV
from gearlister.items import load_items
from gearlister.reverb import Reverb, ReverbError


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--sku", action="append")
    ap.add_argument("--force", action="store_true", help="re-create even if results.csv says done")
    a = ap.parse_args()

    items = [i for i in load_items(ITEMS_CSV, a.sku) if i.list_on_reverb]
    if not items:
        raise SystemExit("No items with list_on_reverb=yes and a title in items.csv")
    rv = Reverb()
    done = state.load()
    me = rv.me()
    print(f"Reverb account: {me.get('email') or me.get('shop_name') or 'ok'}  "
          f"({'SANDBOX' if 'sandbox' in rv.base else 'LIVE'})")
    ok = fail = skip = 0
    for item in items:
        if not a.force and (item.sku, "reverb") in done:
            print(f"- {item.sku}: already created ({done[(item.sku, 'reverb')]['url']}), skipping")
            skip += 1
            continue
        try:
            payload = rv.build_payload(item, publish=a.publish)
        except ReverbError as e:
            print(f"x {item.sku}: {e}")
            fail += 1
            continue
        if a.dry_run:
            print(f"\n--- {item.sku} ---\n{json.dumps(payload, indent=2)}")
            continue
        try:
            listing = rv.create_listing(payload)
            lid = str(listing.get("id", ""))
            url = rv.listing_url(listing)
            status = "published" if a.publish else "created"
            state.record(item.sku, "reverb", status, lid, url, listing.get("state", {}).get("slug", ""))
            print(f"+ {item.sku}: {status} draft id={lid} {url}")
            ok += 1
        except ReverbError as e:
            state.record(item.sku, "reverb", "error", note=str(e))
            print(f"x {item.sku}: {e}")
            fail += 1
    if not a.dry_run:
        print(f"\nDone. created={ok} failed={fail} skipped={skip}. Log: out/results.csv")
        print("Review drafts at https://reverb.com/my/selling/drafts")


if __name__ == "__main__":
    main()
