"""Minimal Reverb API client (api.reverb.com, API version 3.0)."""
import json

import requests

from . import config
from .items import Item


class ReverbError(Exception):
    pass


class Reverb:
    def __init__(self, token: str | None = None, sandbox: bool | None = None,
                 allow_anonymous: bool = False):
        self.token = token or config.REVERB_TOKEN
        if not self.token and not allow_anonymous:
            raise SystemExit("REVERB_TOKEN is not set in .env")
        sandbox = config.REVERB_SANDBOX if sandbox is None else sandbox
        host = "sandbox.reverb.com" if sandbox else "api.reverb.com"
        self.base = f"https://{host}/api"
        self.site = "https://sandbox.reverb.com" if sandbox else "https://reverb.com"
        self.s = requests.Session()
        self.s.headers.update({
            **({"Authorization": f"Bearer {self.token}"} if self.token else {}),
            "Content-Type": "application/hal+json",
            "Accept": "application/hal+json",
            "Accept-Version": "3.0",
            "Accept-Language": "en",
            "X-Display-Currency": config.REVERB_CURRENCY,
        })
        self._conditions: dict[str, str] | None = None
        self._categories: list[dict] | None = None

    # ---- low level ----
    def _req(self, method: str, path: str, **kw) -> dict:
        r = self.s.request(method, f"{self.base}{path}", timeout=60, **kw)
        try:
            data = r.json() if r.text else {}
        except ValueError:
            data = {"raw": r.text}
        if r.status_code >= 400:
            msg = data.get("message") or data.get("errors") or data
            raise ReverbError(f"{method} {path} -> HTTP {r.status_code}: {msg}")
        return data

    def get(self, path: str, **params) -> dict:
        return self._req("GET", path, params=params)

    def post(self, path: str, body: dict) -> dict:
        return self._req("POST", path, data=json.dumps(body))

    def put(self, path: str, body: dict) -> dict:
        return self._req("PUT", path, data=json.dumps(body))

    # ---- lookups ----
    def me(self) -> dict:
        return self.get("/my/account")

    def conditions(self) -> dict[str, str]:
        """Returns {slug: uuid} for listing conditions, e.g. 'very-good' -> uuid."""
        if self._conditions is None:
            data = self.get("/listing_conditions")
            out = {}
            for c in data.get("conditions", data.get("listing_conditions", [])):
                name = c.get("display_name") or c.get("name") or ""
                slug = c.get("slug") or name.lower().replace(" ", "-")
                out[slug] = c["uuid"]
            self._conditions = out
        return self._conditions

    def categories(self) -> list[dict]:
        if self._categories is None:
            data = self.get("/categories/flat")
            self._categories = data.get("categories", [])
        return self._categories

    def find_category(self, query: str) -> dict | None:
        """Match on exact slug or uuid first, then case-insensitive full name."""
        q = query.strip().lower()
        if not q:
            return None
        for c in self.categories():
            if q in (str(c.get("slug", "")).lower(), str(c.get("uuid", "")).lower()):
                return c
        for c in self.categories():
            if q == str(c.get("full_name", "")).lower():
                return c
        matches = [c for c in self.categories() if q in str(c.get("full_name", "")).lower()]
        return matches[0] if len(matches) == 1 else None

    def search_categories(self, query: str) -> list[dict]:
        q = query.strip().lower()
        return [
            c for c in self.categories()
            if q in str(c.get("full_name", "")).lower() or q in str(c.get("slug", "")).lower()
        ]

    def shipping_profiles(self) -> list[dict]:
        data = self.get("/shop/shipping_profiles")
        return data.get("shipping_profiles", data.get("profiles", []))

    # ---- listings ----
    def build_payload(self, item: Item, publish: bool = False) -> dict:
        conds = self.conditions()
        cond_uuid = conds.get(item.condition)
        if not cond_uuid:
            raise ReverbError(
                f"{item.sku}: Reverb has no condition '{item.condition}'. Known: {', '.join(conds)}"
            )
        cat = self.find_category(item.reverb_category)
        if not cat:
            raise ReverbError(
                f"{item.sku}: reverb_category '{item.reverb_category}' not found. "
                f"Run: python reverb_setup.py --find \"{item.reverb_category or 'guitar'}\""
            )
        cur = config.REVERB_CURRENCY
        payload: dict = {
            "make": item.make,
            "model": item.model,
            "title": item.title,
            "description": item.description or item.title,
            "condition": {"uuid": cond_uuid},
            "categories": [{"uuid": cat["uuid"]}],
            "price": {"amount": str(item.price_gbp), "currency": cur},
            "photos": item.photos,
            "sku": item.sku,
            "has_inventory": True,
            "inventory": item.quantity,
            "offers_enabled": item.offers_enabled,
            "publish": publish,
        }
        if item.year:
            payload["year"] = item.year
        if item.finish:
            payload["finish"] = item.finish
        if config.REVERB_SHIPPING_PROFILE_ID:
            payload["shipping_profile_id"] = config.REVERB_SHIPPING_PROFILE_ID
        else:
            rates = []
            if item.shipping_gb_gbp is not None:
                rates.append({"region_code": "GB",
                              "rate": {"amount": str(item.shipping_gb_gbp), "currency": cur}})
            if item.shipping_everywhere_gbp is not None:
                rates.append({"region_code": "XX",
                              "rate": {"amount": str(item.shipping_everywhere_gbp), "currency": cur}})
            if rates:
                payload["shipping"] = {"rates": rates, "local": False}
        return payload

    def create_listing(self, payload: dict) -> dict:
        data = self.post("/listings", payload)
        listing = data.get("listing", data)
        return listing

    def listing_url(self, listing: dict) -> str:
        links = listing.get("_links", {})
        if "web" in links:
            return links["web"].get("href", "")
        lid = listing.get("id")
        return f"{self.site}/item/{lid}" if lid else ""

    def publish(self, listing_id: str) -> dict:
        return self.put(f"/listings/{listing_id}", {"publish": True})

    # ---- reading listings ----
    def _paginate(self, path: str, **params) -> list[dict]:
        params.setdefault("per_page", 50)
        out: list[dict] = []
        page = 1
        while True:
            data = self.get(path, page=page, **params)
            rows = data.get("listings", [])
            out.extend(rows)
            total_pages = int(data.get("total_pages") or 1)
            if not rows or page >= total_pages:
                break
            page += 1
        return out

    def my_listings(self, state: str = "all") -> list[dict]:
        """All of your listings including drafts. state: all | live | draft | ended | sold."""
        return self._paginate("/my/listings", state=state)

    def shop_listings(self, shop_slug: str) -> list[dict]:
        """Public live listings of any shop (no token needed for the data, token still sent if set)."""
        return self._paginate("/listings/all", shop=shop_slug)
