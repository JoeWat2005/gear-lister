"""Runs both platforms in one go.

  python list_all.py                       # Reverb drafts + eBay verify only
  python list_all.py --ebay-schedule 2026-11-07T19:00:00
  python list_all.py --ebay-go --reverb-publish
"""
import argparse
import subprocess
import sys

from gearlister.config import ROOT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reverb-publish", action="store_true")
    ap.add_argument("--ebay-go", action="store_true")
    ap.add_argument("--ebay-schedule")
    ap.add_argument("--sku", action="append")
    a = ap.parse_args()
    skus = [x for s in (a.sku or []) for x in ("--sku", s)]

    rv = [sys.executable, str(ROOT / "list_reverb.py"), *skus]
    if a.reverb_publish:
        rv.append("--publish")
    eb = [sys.executable, str(ROOT / "list_ebay.py"), *skus]
    if a.ebay_go:
        eb.append("--go")
    elif a.ebay_schedule:
        eb += ["--schedule", a.ebay_schedule]

    print("=" * 20, "REVERB", "=" * 20)
    r1 = subprocess.run(rv, cwd=ROOT).returncode
    print("\n" + "=" * 20, "EBAY", "=" * 20)
    r2 = subprocess.run(eb, cwd=ROOT).returncode
    sys.exit(r1 or r2)


if __name__ == "__main__":
    main()
