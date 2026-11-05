"""Pull the live state of your eBay listings: bids, current price, watchers, time left.

  python ebay_status.py            # active listings (auctions first, soonest ending first)
  python ebay_status.py --sold     # also show items sold in the last 60 days
  python ebay_status.py --csv      # also write out/ebay_status.csv
"""
import argparse
import csv
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from gearlister import state
from gearlister.config import OUT_DIR
from gearlister.ebay import NS, EbayTrading


def t(el: ET.Element | None, path: str, default: str = "") -> str:
    if el is None:
        return default
    return el.findtext("/".join(f"{{{NS}}}{p}" for p in path.split("/")), default) or default


def sku_map() -> dict[str, str]:
    out = {}
    for (sku, platform), row in state.load().items():
        if platform == "ebay" and row.get("id"):
            out[row["id"]] = sku
    return out


def fetch(tr: EbayTrading, container: str) -> list[ET.Element]:
    items, page = [], 1
    while True:
        root = tr.call("GetMyeBaySelling", (
            f"<{container}><Include>true</Include>"
            f"<Pagination><EntriesPerPage>200</EntriesPerPage><PageNumber>{page}</PageNumber></Pagination>"
            f"</{container}><DetailLevel>ReturnAll</DetailLevel>"
        ))
        node = root.find(f"{{{NS}}}{container}")
        if node is None:
            break
        found = list(node.iter(f"{{{NS}}}Item"))
        items.extend(found)
        total = int(t(node, "PaginationResult/TotalNumberOfPages", "1") or 1)
        if page >= total or not found:
            break
        page += 1
    return items


def parse_duration(iso: str) -> int:
    """eBay TimeLeft like P8DT21H22M40S -> seconds."""
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def fmt_left(secs: int) -> str:
    if secs <= 0:
        return "ended"
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    return f"{d}d {h}h" if d else (f"{h}h {m:02d}m" if h else f"{m}m")


def row_for(item: ET.Element, skus: dict[str, str], now: datetime) -> dict:
    item_id = t(item, "ItemID")
    ltype = t(item, "ListingType")
    bids = int(t(item, "SellingStatus/BidCount", "0") or 0)
    cur = float(t(item, "SellingStatus/CurrentPrice", "0") or 0)
    start = float(t(item, "StartPrice", "0") or 0)
    bin_ = float(t(item, "BuyItNowPrice", "0") or 0)
    reserve = float(t(item, "ReservePrice", "0") or 0)
    reserve_met = t(item, "SellingStatus/ReserveMet")
    high = t(item, "SellingStatus/HighBidder/UserID")
    left = parse_duration(t(item, "TimeLeft"))
    end = t(item, "ListingDetails/EndTime") or (now + timedelta(seconds=left)).isoformat(timespec="minutes") if left else t(item, "ListingDetails/EndTime")
    return {
        "sku": t(item, "SKU") or skus.get(item_id, ""),
        "item_id": item_id,
        "title": t(item, "Title"),
        "format": "auction" if ltype == "Chinese" else "fixed",
        "start_gbp": start,
        "current_gbp": cur,
        "bids": bids,
        "high_bidder": high,
        "reserve_gbp": reserve,
        "reserve_met": reserve_met,
        "buy_it_now_gbp": bin_,
        "watchers": int(t(item, "WatchCount", "0") or 0),
        "views": t(item, "HitCount"),
        "ends": end,
        "time_left": fmt_left(left) if left else "",
        "url": t(item, "ListingDetails/ViewItemURL") or f"https://www.ebay.co.uk/itm/{item_id}",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sold", action="store_true", help="also list sold items (last 60 days)")
    ap.add_argument("--csv", action="store_true", help="write out/ebay_status.csv")
    args = ap.parse_args()

    tr = EbayTrading()
    skus = sku_map()
    now = datetime.now(timezone.utc)

    active = [row_for(i, skus, now) for i in fetch(tr, "ActiveList")]
    active.sort(key=lambda r: (r["format"] != "auction", r["ends"]))

    auctions = [r for r in active if r["format"] == "auction"]
    fixed = [r for r in active if r["format"] != "auction"]
    with_bids = [r for r in auctions if r["bids"]]
    total_bid = sum(r["current_gbp"] for r in with_bids)
    total_start = sum(r["start_gbp"] for r in auctions)

    print(f"Active: {len(active)} listings ({len(auctions)} auctions, {len(fixed)} fixed price)")
    met = [r for r in with_bids if not r["reserve_gbp"] or r["reserve_met"] == "true"]
    print(f"Auctions with bids: {len(with_bids)}/{len(auctions)} (reserve met or no reserve: {len(met)}, GBP {sum(r['current_gbp'] for r in met):,.2f})   "
          f"total current bids: GBP {total_bid:,.2f}   total bids placed: {sum(r['bids'] for r in auctions)}   "
          f"watchers: {sum(r['watchers'] for r in active)}")
    print()
    hdr = f"{'time left':>9}  {'bids':>4}  {'current':>9}  {'start':>8}  {'reserve':>9}  {'watch':>5}  title"
    print(hdr)
    print("-" * len(hdr))
    for r in auctions:
        if r["reserve_gbp"]:
            rsv = f"{r['reserve_gbp']:.0f}" + (" ok" if r["reserve_met"] == "true" else " no")
        else:
            rsv = "-"
        cur = f"{r['current_gbp']:9.2f}" if r["bids"] else f"{'-':>9}"
        print(f"{r['time_left']:>9}  {r['bids']:4d}  {cur}  {r['start_gbp']:8.2f}  {rsv:>9}  {r['watchers']:5d}  {r['title'][:60]}")
    if fixed:
        print("\nFixed price:")
        for r in fixed:
            print(f"{r['time_left']:>9}  {'':4}  {r['current_gbp']:9.2f}  {'':8}  {'':9}  {r['watchers']:5d}  {r['title'][:60]}")

    sold = []
    if args.sold:
        # SoldList nests Item inside OrderTransaction/Transaction; fetch() flattens with iter().
        sold = [row_for(i, skus, now) for i in fetch(tr, "SoldList")]
        print(f"\nSold (last 60 days): {len(sold)}   total GBP {sum(r['current_gbp'] for r in sold):,.2f}")
        for r in sold:
            print(f"  {r['current_gbp']:9.2f}  {r['title'][:60]}")

    if args.csv:
        OUT_DIR.mkdir(exist_ok=True)
        path = OUT_DIR / "ebay_status.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(active[0].keys()) if active else ["item_id"])
            w.writeheader()
            for r in active + sold:
                w.writerow(r)
        print(f"\nWrote {path}")


if __name__ == "__main__":
    main()
