"""Amazon Creators API adapter (official OAuth/GetItems protocol, September 2026).

https://affiliate-program.amazon.com/creatorsapi/docs/en-us/get-started/using-curl
https://affiliate-program.amazon.com/creatorsapi/docs/en-us/api-reference/operations/get-items
https://affiliate-program.amazon.com/creatorsapi/docs/en-us/api-reference/resources/offersV2
https://affiliate-program.amazon.com/creatorsapi/docs/en-us/concepts/best-programming-practices
No scraping, image downloading, link rewriting or PA-API fallback.
"""
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .amazon_models import MARKETPLACES


class AmazonError(ValueError):
    """Safe operator-facing error; never include provider bodies or credentials."""


class AmazonConfigurationError(AmazonError):
    pass


TOKEN_ENDPOINTS = {
    "3.1": "https://api.amazon.com/auth/o2/token",
    "3.2": "https://api.amazon.co.uk/auth/o2/token",
    "3.3": "https://api.amazon.co.jp/auth/o2/token",
}
API_URL = "https://creatorsapi.amazon/catalog/v1/getItems"
IMAGE_HOSTS = {"m.media-amazon.com", "images-na.ssl-images-amazon.com", "images-eu.ssl-images-amazon.com", "images-fe.ssl-images-amazon.com", "images.amazon.com"}
RESOURCES = ["itemInfo.title", "images.primary.large", "offersV2.listings.price", "offersV2.listings.availability", "offersV2.listings.isBuyBoxWinner", "offersV2.listings.dealDetails", "offersV2.listings.type"]


def safe_url(value, hosts):
    if not isinstance(value, str) or not value or len(value) > 2000 or any(ord(x) < 33 for x in value) or "\\" in value:
        raise AmazonError("Amazon returned an invalid product URL.")
    try:
        parsed = urlsplit(value)
        valid = parsed.scheme == "https" and parsed.hostname in hosts and not parsed.username and not parsed.password and parsed.port in (None, 443)
    except ValueError:
        valid = False
    if not valid:
        raise AmazonError("Amazon returned an unsafe product URL.")
    return value


def text_value(value, limit, *, required=False):
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > limit or any(ord(c) < 32 for c in value):
        raise AmazonError("Amazon returned invalid product text.")
    return value


def parse_item(payload, asin, marketplace):
    if not isinstance(payload, dict):
        raise AmazonError("Amazon returned an invalid response.")
    # Both spellings occur in Amazon's current GetItems/OffersV2 examples.
    container = payload.get("itemResults", payload.get("itemsResult", {}))
    items = container.get("items", []) if isinstance(container, dict) else []
    if not isinstance(items, list):
        raise AmazonError("Amazon returned an invalid item collection.")
    matches = [item for item in items if isinstance(item, dict) and item.get("asin") == asin]
    if len(matches) != 1:
        raise AmazonError("The ASIN is unavailable or inaccessible through Creators API.")
    item = matches[0]
    try:
        title = text_value(item["itemInfo"]["title"]["displayValue"], 500, required=True)
        detail_url = safe_url(item["detailPageURL"], {marketplace, marketplace.removeprefix("www.")})
        if not re.search(r"/(?:dp|gp/product)/" + re.escape(asin) + r"(?:/|$)", urlsplit(detail_url).path):
            raise AmazonError("Amazon returned a product link that does not match the requested ASIN.")
        primary = (item.get("images") or {}).get("primary") or {}
        image = next((primary[size].get("url", "") for size in ("large", "medium", "small") if isinstance(primary.get(size), dict) and primary[size].get("url")), "")
        if image:
            image = safe_url(image, IMAGE_HOSTS)
            if len(image) > 1500:
                raise AmazonError("Amazon returned an image URL exceeding the supported length.")
        listings = (item.get("offersV2") or {}).get("listings") or []
        if not isinstance(listings, list):
            raise TypeError
        # Only an unrestricted current buy-box offer is suitable for the public price.
        offer = next((row for row in listings if isinstance(row, dict) and row.get("isBuyBoxWinner") is True
                      and row.get("violatesMAP") is not True
                      and row.get("type", "") not in ("SUBSCRIBE_AND_SAVE", "SUBSCRIBEAND_SAVE")
                      and (row.get("dealDetails") or {}).get("accessType", "ALL") == "ALL"), {})
        money = (offer.get("price") or {}).get("money") or {}
        price, currency, display_price = None, "", ""
        availability = text_value((offer.get("availability") or {}).get("type", ""), 80)
        offer_valid_until = None
        deal = offer.get("dealDetails") or {}
        if deal.get("endTime"):
            offer_valid_until = parse_datetime(deal["endTime"])
            if offer_valid_until is None or timezone.is_naive(offer_valid_until):
                raise ValueError
            if offer_valid_until <= timezone.now():
                money = {}
        if deal.get("startTime"):
            starts_at = parse_datetime(deal["startTime"])
            if starts_at is None or timezone.is_naive(starts_at):
                raise ValueError
            if starts_at > timezone.now():
                money = {}
        if money and availability in ("IN_STOCK", "INSTOCK", "INSTOCKSCARCE", "PREORDER", "LEADTIME"):
            price = Decimal(str(money["amount"]))
            if not price.is_finite() or price < 0 or price > Decimal("9999999999.99") or price != price.quantize(Decimal("0.01")):
                raise ValueError
            currency = money["currency"]
            if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
                raise ValueError
            display_price = text_value(money.get("displayAmount", ""), 100)
        return {"title": title, "detail_url": detail_url, "image_url": image, "price": price, "currency": currency, "display_price": display_price, "availability": availability, "offer_valid_until": offer_valid_until}
    except (KeyError, TypeError, AttributeError, ValueError, InvalidOperation) as exc:
        if isinstance(exc, AmazonError):
            raise
        raise AmazonError("Amazon returned incomplete or invalid product data.") from None


class CreatorsClient:
    def __init__(self):
        self.client_id = str(getattr(settings, "AMAZON_CREATORS_CLIENT_ID", "")).strip()
        self.client_secret = str(getattr(settings, "AMAZON_CREATORS_CLIENT_SECRET", "")).strip()
        self.version = str(getattr(settings, "AMAZON_CREATORS_CREDENTIAL_VERSION", "3.1"))
        self.partner_tag = str(getattr(settings, "AMAZON_PARTNER_TAG", "")).strip()
        self.marketplace = str(getattr(settings, "AMAZON_MARKETPLACE", "www.amazon.com"))
        self.timeout = min(30, max(1, int(getattr(settings, "AMAZON_HTTP_TIMEOUT", 15))))
        if not self.client_id or not self.client_secret or not self.partner_tag:
            raise AmazonConfigurationError("Configure Amazon Creators client ID, client secret and partner tag before synchronization.")
        if self.version not in TOKEN_ENDPOINTS or self.marketplace not in MARKETPLACES:
            raise AmazonConfigurationError("Configure a supported Creators credential version and Amazon marketplace.")
        digest = hashlib.sha256(f"{self.version}:{self.client_id}:{self.client_secret}".encode()).hexdigest()
        self.token_key = f"amazon-creators-token:{digest}"

    def _post(self, url, payload, headers):
        try:
            with requests.post(url, json=payload, headers=headers, timeout=(5, self.timeout), allow_redirects=False, stream=True) as response:
                if response.status_code != 200:
                    if response.status_code == 401:
                        cache.delete(self.token_key)
                    raise AmazonError(f"Amazon request failed with HTTP {response.status_code}; check credentials, access and API limits.")
                data = bytearray()
                for chunk in response.iter_content(4096):
                    data.extend(chunk)
                    if len(data) > 40 * 1024:
                        raise AmazonError("Amazon response exceeded the permitted response size.")
                parsed = json.loads(data)
                if not isinstance(parsed, dict):
                    raise ValueError
                return parsed
        except (requests.RequestException, ValueError, UnicodeError) as exc:
            if isinstance(exc, AmazonError):
                raise
            raise AmazonError("Amazon request failed or returned invalid JSON.") from None

    def token(self):
        existing = cache.get(self.token_key)
        if existing:
            return existing
        result = self._post(TOKEN_ENDPOINTS[self.version], {
            "grant_type": "client_credentials", "client_id": self.client_id,
            "client_secret": self.client_secret, "scope": "creatorsapi::default",
        }, {"Content-Type": "application/json"})
        token = result.get("access_token")
        if not isinstance(token, str) or not token or len(token) > 10000 or "\r" in token or "\n" in token:
            raise AmazonError("Amazon did not return a valid access token.")
        try:
            lifetime = int(result.get("expires_in", 0))
        except (ValueError, TypeError):
            lifetime = 0
        if lifetime < 60:
            raise AmazonError("Amazon returned an invalid token lifetime.")
        cache.set(self.token_key, token, timeout=min(lifetime, 3600) - 30)
        return token

    def get_item(self, asin, marketplace):
        if marketplace != self.marketplace:
            raise AmazonConfigurationError("The source marketplace must match AMAZON_MARKETPLACE and its registered partner tag.")
        if not re.fullmatch(r"[A-Z0-9]{10}", asin):
            raise AmazonError("Invalid ASIN.")
        payload = self._post(API_URL, {
            "itemIds": [asin], "itemIdType": "ASIN", "marketplace": marketplace,
            "partnerTag": self.partner_tag, "condition": "New", "resources": RESOURCES,
        }, {"Authorization": f"Bearer {self.token()}", "Content-Type": "application/json", "x-marketplace": marketplace})
        return parse_item(payload, asin, marketplace)
