"""Reads items.csv into Item objects and validates them."""
import csv
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

CONDITIONS = {
    # reverb slug : (reverb display name, ebay ConditionID)
    "brand-new": ("Brand New", 1000),
    "b-stock": ("B-Stock", 1500),
    "mint": ("Mint", 3000),
    "excellent": ("Excellent", 3000),
    "very-good": ("Very Good", 3000),
    "good": ("Good", 3000),
    "fair": ("Fair", 3000),
    "poor": ("Poor", 3000),
    "non-functioning": ("Non Functioning", 7000),
}

EBAY_FORMATS = {"auction": "Chinese", "fixed": "FixedPriceItem"}


@dataclass
class Item:
    sku: str
    title: str
    make: str
    model: str
    condition: str
    description: str
    price_gbp: Decimal
    photos: list[str]
    reverb_category: str = ""
    ebay_category_id: str = ""
    year: str = ""
    finish: str = ""
    quantity: int = 1
    shipping_gb_gbp: Decimal | None = None
    shipping_everywhere_gbp: Decimal | None = None
    offers_enabled: bool = True
    ebay_format: str = "auction"
    auction_start_gbp: Decimal | None = None
    reserve_gbp: Decimal | None = None
    buy_it_now_gbp: Decimal | None = None
    ebay_duration: str = "Days_7"
    ebay_specifics: dict[str, str] = field(default_factory=dict)
    ebay_title: str = ""  # optional shorter title for eBay (80 char limit); falls back to title
    ebay_postage: str = ""  # collection | small | medium | large -> postage policy tier in .env
    list_on_reverb: bool = True
    list_on_ebay: bool = True
    row: int = 0

    @property
    def ebay_condition_id(self) -> int:
        return CONDITIONS[self.condition][1]

    @property
    def reverb_condition_name(self) -> str:
        return CONDITIONS[self.condition][0]


def _dec(value: str, name: str, row: int, required: bool = False) -> Decimal | None:
    value = (value or "").strip().replace("£", "").replace(",", "")
    if not value:
        if required:
            raise ValueError(f"row {row}: {name} is required")
        return None
    try:
        return Decimal(value).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise ValueError(f"row {row}: {name} '{value}' is not a number") from None


def _bool(value: str, default: bool) -> bool:
    value = (value or "").strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "y")


def _specifics(value: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in (value or "").split(";"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            if k.strip() and v.strip():
                out[k.strip()] = v.strip()
    return out


def load_items(path: Path, skus: list[str] | None = None) -> list[Item]:
    """Returns items with a title filled in. Rows with an empty title are skipped."""
    items: list[Item] = []
    errors: list[str] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for n, raw in enumerate(csv.DictReader(f), start=2):
            r = {k.strip(): (v or "") for k, v in raw.items() if k}
            if not r.get("title", "").strip():
                continue
            if skus and r.get("sku", "").strip() not in skus:
                continue
            try:
                cond = r.get("condition", "").strip().lower()
                if cond not in CONDITIONS:
                    raise ValueError(
                        f"row {n}: condition '{cond}' must be one of {', '.join(CONDITIONS)}"
                    )
                fmt = (r.get("ebay_format", "") or "auction").strip().lower()
                if fmt not in EBAY_FORMATS:
                    raise ValueError(f"row {n}: ebay_format must be auction or fixed")
                photos = [p.strip() for p in r.get("photos", "").split("|") if p.strip()]
                item = Item(
                    sku=r.get("sku", "").strip() or f"ROW{n}",
                    title=r["title"].strip(),
                    make=r.get("make", "").strip(),
                    model=r.get("model", "").strip(),
                    condition=cond,
                    description=r.get("description", "").strip(),
                    price_gbp=_dec(r.get("price_gbp"), "price_gbp", n, required=True),
                    photos=photos,
                    reverb_category=r.get("reverb_category", "").strip(),
                    ebay_category_id=r.get("ebay_category_id", "").strip(),
                    year=r.get("year", "").strip(),
                    finish=r.get("finish", "").strip(),
                    quantity=int((r.get("quantity") or "1").strip() or 1),
                    shipping_gb_gbp=_dec(r.get("shipping_gb_gbp"), "shipping_gb_gbp", n),
                    shipping_everywhere_gbp=_dec(
                        r.get("shipping_everywhere_gbp"), "shipping_everywhere_gbp", n
                    ),
                    offers_enabled=_bool(r.get("offers_enabled"), True),
                    ebay_format=fmt,
                    auction_start_gbp=_dec(r.get("auction_start_gbp"), "auction_start_gbp", n),
                    reserve_gbp=_dec(r.get("reserve_gbp"), "reserve_gbp", n),
                    buy_it_now_gbp=_dec(r.get("buy_it_now_gbp"), "buy_it_now_gbp", n),
                    ebay_duration=(r.get("ebay_duration") or "Days_7").strip(),
                    ebay_specifics=_specifics(r.get("ebay_specifics", "")),
                    ebay_title=r.get("ebay_title", "").strip(),
                    ebay_postage=r.get("ebay_postage", "").strip().lower(),
                    list_on_reverb=_bool(r.get("list_on_reverb"), True),
                    list_on_ebay=_bool(r.get("list_on_ebay"), True),
                    row=n,
                )
                if not item.make or not item.model:
                    raise ValueError(f"row {n}: make and model are required (Reverb needs them)")
                if item.list_on_ebay and item.ebay_format == "auction" and item.auction_start_gbp is None:
                    raise ValueError(f"row {n}: auction_start_gbp is required for an auction")
                if not item.photos:
                    raise ValueError(f"row {n}: at least one photo URL is required")
                items.append(item)
            except ValueError as e:
                errors.append(str(e))
    if errors:
        raise SystemExit("items.csv has problems:\n  " + "\n  ".join(errors))
    return items
