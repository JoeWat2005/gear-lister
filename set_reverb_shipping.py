"""Set Reverb UK delivery to match the eBay postage tier in items.csv (ebay_postage column).

small = GBP 12, medium = GBP 30, large = GBP 50, all with local pickup kept on.
Rows with a blank ebay_postage are left alone (collection only).

python set_reverb_shipping.py            # preview
python set_reverb_shipping.py --apply    # update, 45-75 s between listings, stops if "under review"
"""
import argparse
import csv
import random
import sys
import time

from gearlister.reverb import Reverb

TIERS = {"small": "12.00", "medium": "30.00", "large": "50.00"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--delay", type=float, default=45)
    a = ap.parse_args()

    rv = Reverb()
    live = {str(l["id"]): l for l in rv.my_listings("all")}
    with open("items.csv", newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("title") or "").strip()]

    plan = []
    for r in rows:
        sku = r["sku"].strip()
        lid = sku.removeprefix("RV-")
        tier = (r.get("ebay_postage") or "").strip().lower()
        l = live.get(lid)
        if not l:
            print(f"- {sku}: not found on Reverb")
            continue
        if tier not in TIERS:
            print(f"- {sku}: no size in ebay_postage, left as collection only")
            continue
        amt = TIERS[tier]
        have = {x.get("region_code"): x["rate"]["amount"] for x in l["shipping"].get("rates", [])}
        if have.get("GB") == amt and l["shipping"].get("local"):
            print(f"- {sku}: already GBP {amt}")
            continue
        plan.append((sku, lid, tier, amt, r["title"][:45]))

    for sku, _, tier, amt, title in plan:
        print(f"  {sku}  {tier:<6} GBP {amt:>6}  {title}")
    print(f"\n{len(plan)} to update.")
    if not a.apply:
        return

    done = 0
    for n, (sku, lid, tier, amt, title) in enumerate(plan):
        if n:
            time.sleep(a.delay + random.uniform(0, 30))
        body = {"shipping": {"local": True,
                             "rates": [{"region_code": "GB", "rate": {"amount": amt, "currency": "GBP"}}]}}
        try:
            rv.put(f"/listings/{lid}", body)
            done += 1
            print(f"+ {sku}: GBP {amt} ({tier}) + collection", flush=True)
        except Exception as e:
            print(f"x {sku}: {e}", flush=True)
            if "under review" in str(e).lower():
                print("Account under review - stopping.")
                sys.exit(1)
    print(f"\nDone: {done}/{len(plan)} updated.")


if __name__ == "__main__":
    main()
