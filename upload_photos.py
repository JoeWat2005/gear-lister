"""Turns local photos into public URLs for the photos column, using eBay Picture Services.

Put photos in  photos/<sku>/*.jpg  then run:

  python upload_photos.py

It uploads each sku's photos (sorted by filename), and writes the resulting URLs into the
photos column of items.csv for that sku (joined with |). Skus that already have URLs are
left alone unless you pass --overwrite. The URLs are public, so Reverb can use them too.
"""
import argparse
import csv
from pathlib import Path

from gearlister.config import ITEMS_CSV, ROOT
from gearlister.ebay import EbayError, EbayTrading

PHOTO_DIR = ROOT / "photos"
EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    if not PHOTO_DIR.exists():
        raise SystemExit(f"Create {PHOTO_DIR} with one sub-folder per sku, e.g. photos/ITEM-001/")
    with open(ITEMS_CSV, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)
    tr = EbayTrading()
    changed = 0
    for row in rows:
        sku = (row.get("sku") or "").strip()
        folder = PHOTO_DIR / sku
        if not sku or not folder.is_dir():
            continue
        if (row.get("photos") or "").strip() and not a.overwrite:
            print(f"- {sku}: already has photo URLs, skipping")
            continue
        files = sorted(p for p in folder.iterdir() if p.suffix.lower() in EXTS)
        if not files:
            continue
        urls = []
        for p in files[:24]:
            try:
                urls.append(tr.upload_picture(p))
                print(f"  {sku}: {p.name} -> ok")
            except EbayError as e:
                print(f"  {sku}: {p.name} FAILED: {e}")
        if urls:
            row["photos"] = "|".join(urls)
            changed += 1
    with open(ITEMS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"\nUpdated photos for {changed} sku(s) in items.csv")


if __name__ == "__main__":
    main()
