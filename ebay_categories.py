"""Suggests ebay.co.uk category IDs for a search phrase.

  python ebay_categories.py --find "fender stratocaster electric guitar"
"""
import argparse

from gearlister.ebay import EbayAuth, suggest_categories


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--find", required=True)
    a = ap.parse_args()
    for c in suggest_categories(EbayAuth(), a.find):
        print(f"{c['id']:>8}  {c['path']} > {c['name']}")


if __name__ == "__main__":
    main()
