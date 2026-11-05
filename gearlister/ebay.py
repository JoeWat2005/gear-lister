"""eBay OAuth + Trading API (AddItem / VerifyAddItem) + picture upload + policy lookups."""
import base64
import json
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape

import requests

from . import config
from .items import EBAY_FORMATS, Item

HOSTS = {
    "production": {
        "api": "https://api.ebay.com",
        "auth": "https://auth.ebay.com/oauth2/authorize",
        "trading": "https://api.ebay.com/ws/api.dll",
    },
    "sandbox": {
        "api": "https://api.sandbox.ebay.com",
        "auth": "https://auth.sandbox.ebay.com/oauth2/authorize",
        "trading": "https://api.sandbox.ebay.com/ws/api.dll",
    },
}
USER_SCOPES = [
    "https://api.ebay.com/oauth/api_scope",
    "https://api.ebay.com/oauth/api_scope/sell.inventory",
    "https://api.ebay.com/oauth/api_scope/sell.account",
]
NS = "urn:ebay:apis:eBLBaseComponents"


class EbayError(Exception):
    pass


def _hosts() -> dict:
    if config.EBAY_ENV not in HOSTS:
        raise SystemExit("EBAY_ENV must be production or sandbox")
    return HOSTS[config.EBAY_ENV]


# ---------------------------------------------------------------- OAuth
class EbayAuth:
    def __init__(self):
        self.client_id = config.EBAY_CLIENT_ID
        self.client_secret = config.EBAY_CLIENT_SECRET
        if not self.client_id or not self.client_secret:
            raise SystemExit("EBAY_CLIENT_ID / EBAY_CLIENT_SECRET not set in .env")
        self.token_url = f"{_hosts()['api']}/identity/v1/oauth2/token"

    def _basic(self) -> dict:
        raw = f"{self.client_id}:{self.client_secret}".encode()
        return {"Authorization": "Basic " + base64.b64encode(raw).decode(),
                "Content-Type": "application/x-www-form-urlencoded"}

    def consent_url(self) -> str:
        if not config.EBAY_RUNAME:
            raise SystemExit("EBAY_RUNAME not set in .env (your app's RuName from the developer portal)")
        q = urllib.parse.urlencode({
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": config.EBAY_RUNAME,
            "scope": " ".join(USER_SCOPES),
        })
        return f"{_hosts()['auth']}?{q}"

    def exchange_code(self, code: str) -> dict:
        code = urllib.parse.unquote(code)
        r = requests.post(self.token_url, headers=self._basic(), data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": config.EBAY_RUNAME,
        }, timeout=60)
        if r.status_code != 200:
            raise EbayError(f"Token exchange failed: {r.status_code} {r.text}")
        tok = r.json()
        tok["obtained_at"] = int(time.time())
        self.save(tok)
        return tok

    def refresh(self, refresh_token: str) -> dict:
        r = requests.post(self.token_url, headers=self._basic(), data={
            "grant_type": "refresh_token", "refresh_token": refresh_token,
            "scope": " ".join(USER_SCOPES),
        }, timeout=60)
        if r.status_code != 200:
            raise EbayError(f"Token refresh failed: {r.status_code} {r.text}. Re-run ebay_auth.py")
        tok = r.json()
        tok["refresh_token"] = refresh_token
        tok["obtained_at"] = int(time.time())
        self.save(tok)
        return tok

    def app_token(self) -> str:
        """Client-credentials token for public APIs like Taxonomy."""
        r = requests.post(self.token_url, headers=self._basic(), data={
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        }, timeout=60)
        if r.status_code != 200:
            raise EbayError(f"App token failed: {r.status_code} {r.text}")
        return r.json()["access_token"]

    @staticmethod
    def save(tok: dict):
        config.EBAY_TOKEN_FILE.write_text(json.dumps(tok, indent=2))

    def user_token(self) -> str:
        if not config.EBAY_TOKEN_FILE.exists():
            raise SystemExit("No eBay user token yet. Run: python ebay_auth.py")
        tok = json.loads(config.EBAY_TOKEN_FILE.read_text())
        age = time.time() - tok.get("obtained_at", 0)
        if age > tok.get("expires_in", 7200) - 120:
            tok = self.refresh(tok["refresh_token"])
        return tok["access_token"]


# ---------------------------------------------------------------- Trading API
def _text(tag: str, value) -> str:
    return f"<{tag}>{escape(str(value))}</{tag}>"


class EbayTrading:
    def __init__(self, auth: EbayAuth | None = None):
        self.auth = auth or EbayAuth()
        self.url = _hosts()["trading"]

    def _headers(self, call: str) -> dict:
        return {
            "X-EBAY-API-SITEID": config.EBAY_SITE_ID,
            "X-EBAY-API-COMPATIBILITY-LEVEL": "1225",
            "X-EBAY-API-CALL-NAME": call,
            "X-EBAY-API-IAF-TOKEN": self.auth.user_token(),
        }

    def call(self, name: str, inner_xml: str) -> ET.Element:
        body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            f'<{name}Request xmlns="{NS}">'
            "<ErrorLanguage>en_GB</ErrorLanguage><WarningLevel>High</WarningLevel>"
            f"{inner_xml}</{name}Request>"
        )
        r = requests.post(self.url, headers={**self._headers(name), "Content-Type": "text/xml"},
                          data=body.encode("utf-8"), timeout=120)
        return self._parse(r, name)

    def _parse(self, r: requests.Response, name: str) -> ET.Element:
        try:
            root = ET.fromstring(r.text)
        except ET.ParseError:
            raise EbayError(f"{name}: non-XML response ({r.status_code}): {r.text[:300]}")
        ack = root.findtext(f"{{{NS}}}Ack", "")
        errors, warnings = [], []
        for e in root.findall(f"{{{NS}}}Errors"):
            sev = e.findtext(f"{{{NS}}}SeverityCode", "")
            code = e.findtext(f"{{{NS}}}ErrorCode", "")
            msg = e.findtext(f"{{{NS}}}LongMessage") or e.findtext(f"{{{NS}}}ShortMessage", "")
            (warnings if sev == "Warning" else errors).append(f"[{code}] {msg}")
        root.set("warnings", " | ".join(warnings))
        if ack not in ("Success", "Warning"):
            raise EbayError(f"{name} failed: " + ("; ".join(errors) or r.text[:500]))
        return root

    # ---- item XML ----
    def item_xml(self, item: Item, schedule: str | None = None) -> str:
        if not item.ebay_category_id:
            raise EbayError(f"{item.sku}: ebay_category_id is empty. "
                            f"Run: python ebay_categories.py --find \"{item.title}\"")
        cur = config.EBAY_CURRENCY
        is_auction = item.ebay_format == "auction"
        start = item.auction_start_gbp if is_auction else item.price_gbp
        parts = [
            _text("Title", (item.ebay_title or item.title)[:80]),
            f"<Description><![CDATA[{item.description or item.title}]]></Description>",
            f"<PrimaryCategory>{_text('CategoryID', item.ebay_category_id)}</PrimaryCategory>",
            f'<StartPrice currencyID="{cur}">{start}</StartPrice>',
            _text("ConditionID", item.ebay_condition_id),
            _text("Country", config.EBAY_COUNTRY),
            _text("Currency", cur),
            _text("ListingDuration", item.ebay_duration if is_auction else "GTC"),
            _text("ListingType", EBAY_FORMATS[item.ebay_format]),
            _text("Quantity", 1 if is_auction else item.quantity),
            _text("SKU", item.sku),
            _text("Site", config.EBAY_SITE_NAME),
        ]
        if is_auction:
            if item.reserve_gbp is not None:
                parts.append(f'<ReservePrice currencyID="{cur}">{item.reserve_gbp}</ReservePrice>')
            if item.buy_it_now_gbp is not None:
                parts.append(f'<BuyItNowPrice currencyID="{cur}">{item.buy_it_now_gbp}</BuyItNowPrice>')
        if item.ebay_condition_id != 1000 and item.description:
            parts.append(_text("ConditionDescription", item.description[:1000]))
        if config.EBAY_POSTCODE:
            parts.append(_text("PostalCode", config.EBAY_POSTCODE))
        pics = "".join(_text("PictureURL", p) for p in item.photos[:24])
        parts.append(f"<PictureDetails>{pics}</PictureDetails>")

        specifics = {"Brand": item.make, "Model": item.model}
        if item.year:
            specifics["Year"] = item.year
        if item.finish:
            specifics["Colour"] = item.finish
        specifics.update(item.ebay_specifics)
        nv = "".join(
            f"<NameValueList>{_text('Name', k)}{_text('Value', v)}</NameValueList>"
            for k, v in specifics.items()
        )
        parts.append(f"<ItemSpecifics>{nv}</ItemSpecifics>")

        pay, ret = config.EBAY_PAYMENT_POLICY_ID, config.EBAY_RETURN_POLICY_ID
        if item.ebay_postage and item.ebay_postage not in config.EBAY_SHIPPING_POLICY_TIERS:
            raise EbayError(f"{item.sku}: ebay_postage must be one of "
                            f"{', '.join(config.EBAY_SHIPPING_POLICY_TIERS)} (or blank)")
        ship = config.EBAY_SHIPPING_POLICY_TIERS.get(item.ebay_postage) or config.EBAY_SHIPPING_POLICY_ID
        if pay and ret and ship:
            parts.append(
                "<SellerProfiles>"
                f"<SellerPaymentProfile>{_text('PaymentProfileID', pay)}</SellerPaymentProfile>"
                f"<SellerReturnProfile>{_text('ReturnProfileID', ret)}</SellerReturnProfile>"
                f"<SellerShippingProfile>{_text('ShippingProfileID', ship)}</SellerShippingProfile>"
                "</SellerProfiles>"
            )
        else:
            raise EbayError(
                "Set EBAY_PAYMENT_POLICY_ID, EBAY_RETURN_POLICY_ID and EBAY_SHIPPING_POLICY_ID in .env. "
                "Run: python ebay_policies.py to see your IDs."
            )
        if schedule:
            parts.append(_text("ScheduleTime", schedule))
        return "<Item>" + "".join(parts) + "</Item>"

    def verify_add_item(self, item: Item, schedule: str | None = None) -> ET.Element:
        return self.call("VerifyAddItem", self.item_xml(item, schedule))

    def add_item(self, item: Item, schedule: str | None = None) -> ET.Element:
        return self.call("AddItem", self.item_xml(item, schedule))

    @staticmethod
    def item_id(root: ET.Element) -> str:
        return root.findtext(f"{{{NS}}}ItemID", "")

    @staticmethod
    def fees(root: ET.Element) -> str:
        out = []
        for fee in root.iter(f"{{{NS}}}Fee"):
            name = fee.findtext(f"{{{NS}}}Name", "")
            val = fee.find(f"{{{NS}}}Fee")
            if val is not None and val.text not in (None, "0.0", "0"):
                out.append(f"{name}={val.text}")
        return ", ".join(out)

    def item_url(self, item_id: str) -> str:
        host = "www.sandbox.ebay.co.uk" if config.EBAY_ENV == "sandbox" else "www.ebay.co.uk"
        return f"https://{host}/itm/{item_id}" if item_id else ""

    def upload_picture(self, path: Path) -> str:
        """Uploads a local image to eBay Picture Services (Media API) and returns its public URL.

        The old Trading call UploadSiteHostedPictures now returns 404, so this uses
        commerce/media/v1_beta create_image_from_file. Images not used in a listing within
        30 days expire. Phone photos are rotated per their EXIF tag first (if Pillow is installed).
        """
        data = path.read_bytes()
        try:
            import io
            from PIL import Image, ImageOps
            im = Image.open(io.BytesIO(data))
            if im.getexif().get(0x0112, 1) != 1:
                buf = io.BytesIO()
                ImageOps.exif_transpose(im).convert("RGB").save(buf, "JPEG", quality=92)
                data = buf.getvalue()
        except ImportError:
            pass
        host = "https://apim.sandbox.ebay.com" if config.EBAY_ENV == "sandbox" else "https://apim.ebay.com"
        r = requests.post(f"{host}/commerce/media/v1_beta/image/create_image_from_file",
                          headers={"Authorization": f"Bearer {self.auth.user_token()}"},
                          files={"image": (path.name, data, "image/jpeg")}, timeout=180)
        if r.status_code not in (200, 201):
            raise EbayError(f"image upload failed ({r.status_code}): {r.text[:300]}")
        url = r.json().get("imageUrl", "")
        if not url:
            raise EbayError(f"No imageUrl in picture upload response for {path.name}")
        return url


# ---------------------------------------------------------------- REST helpers
def rest_get(path: str, token: str, **params) -> dict:
    r = requests.get(f"{_hosts()['api']}{path}", params=params, timeout=60, headers={
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": config.EBAY_MARKETPLACE_ID,
        "Accept": "application/json",
    })
    if r.status_code >= 400:
        raise EbayError(f"GET {path} -> {r.status_code}: {r.text[:500]}")
    return r.json()


def list_policies(auth: EbayAuth) -> dict[str, list[dict]]:
    tok = auth.user_token()
    mk = config.EBAY_MARKETPLACE_ID
    return {
        "payment": rest_get("/sell/account/v1/payment_policy", tok, marketplace_id=mk)
        .get("paymentPolicies", []),
        "return": rest_get("/sell/account/v1/return_policy", tok, marketplace_id=mk)
        .get("returnPolicies", []),
        "shipping": rest_get("/sell/account/v1/fulfillment_policy", tok, marketplace_id=mk)
        .get("fulfillmentPolicies", []),
    }


def suggest_categories(auth: EbayAuth, query: str) -> list[dict]:
    tok = auth.app_token()
    tree = rest_get("/commerce/taxonomy/v1/get_default_category_tree_id", tok,
                    marketplace_id=config.EBAY_MARKETPLACE_ID)["categoryTreeId"]
    data = rest_get(f"/commerce/taxonomy/v1/category_tree/{tree}/get_category_suggestions",
                    tok, q=query)
    out = []
    for s in data.get("categorySuggestions", []):
        cat = s["category"]
        path = " > ".join(a["categoryName"] for a in reversed(s.get("categoryTreeNodeAncestors", [])))
        out.append({"id": cat["categoryId"], "name": cat["categoryName"], "path": path})
    return out
