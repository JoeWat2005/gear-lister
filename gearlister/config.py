"""Loads settings from the .env file next to this package."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "out"
ITEMS_CSV = ROOT / "items.csv"
EBAY_TOKEN_FILE = ROOT / ".ebay_token.json"

load_dotenv(ROOT / ".env")


def env(name: str, default: str | None = None, required: bool = False) -> str | None:
    value = os.environ.get(name, default)
    if value is not None:
        value = value.strip()
    if required and not value:
        raise SystemExit(f"Missing {name} in .env (see .env.example)")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    value = env(name)
    if value is None or value == "":
        return default
    return value.lower() in ("1", "true", "yes", "y")


# ---- Reverb ----
REVERB_TOKEN = env("REVERB_TOKEN")
REVERB_SANDBOX = env_bool("REVERB_SANDBOX", False)
REVERB_CURRENCY = env("REVERB_CURRENCY", "GBP")
REVERB_SHIPPING_PROFILE_ID = env("REVERB_SHIPPING_PROFILE_ID")

# ---- eBay ----
EBAY_ENV = (env("EBAY_ENV", "production") or "production").lower()
if EBAY_ENV == "sandbox":
    # Sandbox keyset + its own token file, so switching env never mixes up live and test tokens.
    EBAY_CLIENT_ID = env("EBAY_SANDBOX_CLIENT_ID") or env("EBAY_CLIENT_ID")
    EBAY_CLIENT_SECRET = env("EBAY_SANDBOX_CLIENT_SECRET") or env("EBAY_CLIENT_SECRET")
    EBAY_RUNAME = env("EBAY_SANDBOX_RUNAME") or env("EBAY_RUNAME")
    EBAY_TOKEN_FILE = ROOT / ".ebay_token.sandbox.json"
else:
    EBAY_CLIENT_ID = env("EBAY_CLIENT_ID")
    EBAY_CLIENT_SECRET = env("EBAY_CLIENT_SECRET")
    EBAY_RUNAME = env("EBAY_RUNAME")
EBAY_DEV_ID = env("EBAY_DEV_ID")
EBAY_SITE_ID = env("EBAY_SITE_ID", "3")          # 3 = ebay.co.uk
EBAY_SITE_NAME = env("EBAY_SITE_NAME", "UK")
EBAY_MARKETPLACE_ID = env("EBAY_MARKETPLACE_ID", "EBAY_GB")
EBAY_CURRENCY = env("EBAY_CURRENCY", "GBP")
EBAY_COUNTRY = env("EBAY_COUNTRY", "GB")
EBAY_POSTCODE = env("EBAY_POSTCODE")
EBAY_PAYMENT_POLICY_ID = env("EBAY_PAYMENT_POLICY_ID")
EBAY_RETURN_POLICY_ID = env("EBAY_RETURN_POLICY_ID")
EBAY_SHIPPING_POLICY_ID = env("EBAY_SHIPPING_POLICY_ID")
# Optional per-item postage tiers, chosen with the ebay_postage column (collection|small|medium|large).
# Blank ebay_postage, or an unset tier, falls back to EBAY_SHIPPING_POLICY_ID.
EBAY_SHIPPING_POLICY_TIERS = {
    "collection": EBAY_SHIPPING_POLICY_ID,
    "small": env("EBAY_SHIPPING_POLICY_SMALL_ID"),
    "medium": env("EBAY_SHIPPING_POLICY_MEDIUM_ID"),
    "large": env("EBAY_SHIPPING_POLICY_LARGE_ID"),
}
EBAY_DISPATCH_DAYS = env("EBAY_DISPATCH_DAYS", "3")
