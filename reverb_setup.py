"""Checks your Reverb token and looks up category / condition / shipping-profile values.

  python reverb_setup.py                      # test token, list conditions + shipping profiles
  python reverb_setup.py --find "solid body"  # search categories for items.csv reverb_category
"""
import argparse

from gearlister.reverb import Reverb, ReverbError


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--find")
    a = ap.parse_args()
    rv = Reverb()
    if a.find:
        rows = rv.search_categories(a.find)
        if not rows:
            print("No categories matched.")
        for c in rows:
            print(f"{c.get('slug', ''):<45} {c.get('full_name', '')}")
        print("\nPut the slug (left column) in the reverb_category column of items.csv.")
        return
    me = rv.me()
    print(f"Token OK. Account: {me.get('email', '')} shop: {me.get('shop_name', '')}")
    print("\nConditions (use the left value in the condition column):")
    for slug in rv.conditions():
        print(f"  {slug}")
    try:
        print("\nShipping profiles (optional REVERB_SHIPPING_PROFILE_ID in .env):")
        for p in rv.shipping_profiles():
            print(f"  {p.get('id')}  {p.get('name')}")
    except ReverbError as e:
        print(f"  (could not list shipping profiles: {e})")


if __name__ == "__main__":
    main()
