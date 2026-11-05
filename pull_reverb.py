"""Pull your existing Reverb listings (live + drafts) into items.csv, photos included.

  python pull_reverb.py                    # needs REVERB_TOKEN; pulls all states
  python pull_reverb.py --state live       # live | draft | ended | sold | all
  python pull_reverb.py --shop my-shop-slug  # public live listings only, no token needed
  python pull_reverb.py --out pulled.csv   # write somewhere else instead of items.csv

Rows already in items.csv with a title are kept unless the pulled sku matches.
Blank template rows are dropped. Listings that already exist on Reverb are logged in
out/results.csv so list_reverb.py will not create them again.
"""
import argparse
import csv
import re
from html.parser import HTMLParser
from pathlib import Path

from gearlister import state
from gearlister.config import ITEMS_CSV
from gearlister.items import CONDITIONS
from gearlister.reverb import Reverb

COLUMNS = ["sku", "title", "make", "model", "year", "finish", "condition", "description", "price_gbp",
           "reverb_category", "ebay_category_id", "photos", "shipping_gb_gbp", "shipping_everywhere_gbp",
           "offers_enabled", "ebay_format", "auction_start_gbp", "reserve_gbp", "buy_it_now_gbp",
           "ebay_duration", "ebay_specifics", "quantity", "list_on_reverb", "list_on_ebay"]


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, d):
        self.parts.append(d)

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "br", "li", "div", "tr"):
            self.parts.append("\n")


def html_to_text(html: str) -> str:
    t = _Text()
    t.feed(html or "")
    return re.sub(r"\n{3,}", "\n\n", "".join(t.parts)).strip()


def best_photo(photo: dict) -> str:
    links = photo.get("_links", {})
    for key in ("full", "large_crop", "small_crop", "thumbnail"):
        if key in links and links[key].get("href"):
            return links[key]["href"]
    return ""


def to_row(l: dict) -> dict:
    cond = (l.get("condition") or {}).get("slug") or ""
    if cond not in CONDITIONS:
        name = ((l.get("condition") or {}).get("display_name") or "").lower().replace(" ", "-")
        cond = name if name in CONDITIONS else "very-good"
    cats = l.get("categories") or []
    rates = {r.get("region_code"): (r.get("rate") or {}).get("amount", "")
             for r in (l.get("shipping") or {}).get("rates", [])}
    row = {c: "" for c in COLUMNS}
    row.update({
        "sku": (l.get("sku") or "").strip() or f"RV-{l.get('id')}",
        "title": l.get("title", ""),
        "make": l.get("make", ""),
        "model": l.get("model", ""),
        "year": l.get("year", "") or "",
        "finish": l.get("finish", "") or "",
        "condition": cond,
        "description": html_to_text(l.get("description", "")),
        "price_gbp": (l.get("price") or {}).get("amount", ""),
        "reverb_category": cats[0].get("full_name", "") if cats else "",
        "photos": "|".join(p for p in (best_photo(ph) for ph in l.get("photos", [])) if p),
        "shipping_gb_gbp": rates.get("GB", ""),
        "shipping_everywhere_gbp": rates.get("XX", ""),
        "offers_enabled": "yes" if l.get("offers_enabled", True) else "no",
        "ebay_format": "auction",
        "ebay_duration": "Days_7",
        "quantity": str(l.get("inventory") or 1),
        "list_on_reverb": "yes",
        "list_on_ebay": "yes",
    })
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="all")
    ap.add_argument("--shop", help="public shop slug (from your shop URL reverb.com/shop/<slug>)")
    ap.add_argument("--out", default=str(ITEMS_CSV))
    a = ap.parse_args()
    out = Path(a.out)

    rv = Reverb(allow_anonymous=bool(a.shop))
    listings = rv.shop_listings(a.shop) if a.shop else rv.my_listings(a.state)
    print(f"Fetched {len(listings)} listing(s) from Reverb, loading full photo sets...")
    if not listings:
        return
    for l in listings:  # list views only carry the primary photo; the detail view has them all
        try:
            full = rv.get(f"/listings/{l['id']}")
            if full.get("photos"):
                l["photos"] = full["photos"]
            if full.get("description"):
                l["description"] = full["description"]
        except Exception as e:  # noqa: BLE001
            print(f"  (could not load detail for {l.get('id')}: {e})")

    pulled = [to_row(l) for l in listings]
    pulled_skus = {r["sku"] for r in pulled}

    existing: list[dict] = []
    if out.exists():
        with open(out, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                r = {c: (r.get(c) or "") for c in COLUMNS}
                if r["title"].strip() and r["sku"] not in pulled_skus:
                    existing.append(r)

    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(existing + pulled)

    if out.resolve() == ITEMS_CSV.resolve() and not a.shop:
        done = state.load()
        for l, r in zip(listings, pulled):
            if (r["sku"], "reverb") not in done:
                st = (l.get("state") or {}).get("slug", "")
                state.record(r["sku"], "reverb", "created", str(l.get("id", "")),
                             rv.listing_url(l), f"already on reverb ({st})")

    for l, r in zip(listings, pulled):
        st = (l.get("state") or {}).get("slug", "?")
        print(f"  {r['sku']:<14} [{st:<5}] {r['title'][:60]}  photos={len(r['photos'].split('|')) if r['photos'] else 0}")
    print(f"\nWrote {len(existing) + len(pulled)} rows to {out}")
    print("Still to fill for eBay: ebay_category_id and auction_start_gbp (or set ebay_format=fixed).")


if __name__ == "__main__":
    main()
