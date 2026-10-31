from __future__ import annotations

import copy
import json
import math
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PRODUCTS_URL = "https://canboso.com/api/v2/telegram-buyer/products"
PRODUCT_TYPES = {
    "account": "Conta",
    "slot": "Vaga",
    "upgrade_account": "Upgrade de conta",
}


class CanbosoCatalogError(Exception):
    def __init__(self, message: str = "Catálogo do fornecedor temporariamente indisponível.", *, status_code: int = 503, retry_after: int | None = None):
        super().__init__(message)
        self.status_code = status_code if status_code in {429, 503} else 503
        self.retry_after = retry_after if retry_after and retry_after > 0 else None


def _number(value, field: str, *, nullable: bool = False):
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise CanbosoCatalogError(f"Resposta inválida do fornecedor ({field}).")
    return value


def _normalize_product(item: dict) -> dict:
    if not isinstance(item, dict):
        raise CanbosoCatalogError("Resposta inválida do fornecedor (produto).")
    product_id = item.get("productId")
    name = item.get("name")
    product_type = item.get("productType")
    price = item.get("price")
    availability = item.get("availability")
    if not isinstance(product_id, str) or not product_id.strip() or not isinstance(name, str) or not name.strip():
        raise CanbosoCatalogError("Resposta inválida do fornecedor (identificação do produto).")
    if product_type not in PRODUCT_TYPES or not isinstance(price, dict) or not isinstance(availability, dict):
        raise CanbosoCatalogError("Resposta inválida do fornecedor (dados do produto).")
    currency = price.get("currency")
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Za-z]{3}", currency):
        raise CanbosoCatalogError("Resposta inválida do fornecedor (moeda).")
    promotions = item.get("promotions", [])
    if not isinstance(promotions, list):
        raise CanbosoCatalogError("Resposta inválida do fornecedor (promoções).")
    requirements = item.get("purchaseRequirements", {})
    if not isinstance(requirements, dict):
        raise CanbosoCatalogError("Resposta inválida do fornecedor (requisitos).")
    description = item.get("description", "")
    if not isinstance(description, str):
        description = ""
    return {
        "id": product_id.strip(),
        "name": name.strip(),
        "category": PRODUCT_TYPES[product_type],
        "description": description,
        "product_type": product_type,
        "price_amount": _number(price.get("amount"), "preço"),
        "price_currency": currency.upper(),
        "stock": _number(availability.get("available"), "estoque", nullable=True),
        "sold": _number(availability.get("sold", 0), "vendidos"),
        "active": True,
        "promotions": promotions,
        "purchase_requirements": requirements,
    }


def fetch_canboso_catalog(api_key: str) -> dict:
    """Read the authenticated Canboso buyer catalog; never return or log its key."""
    if not isinstance(api_key, str) or not api_key.strip():
        raise CanbosoCatalogError("Chave da API do catálogo não configurada.")
    url = f"{PRODUCTS_URL}?{urlencode({'key': api_key.strip()})}"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "NovaAssinaturasCatalog/1.0"})
    try:
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read())
    except HTTPError as exc:
        retry_after = None
        if exc.code == 429:
            try:
                retry_after = int(exc.headers.get("Retry-After", ""))
            except (TypeError, ValueError):
                retry_after = None
        raise CanbosoCatalogError(status_code=429 if exc.code == 429 else 503, retry_after=retry_after) from None
    except (URLError, TimeoutError, OSError, json.JSONDecodeError, UnicodeDecodeError):
        raise CanbosoCatalogError() from None
    if not isinstance(payload, dict) or payload.get("success") is not True or not isinstance(payload.get("products"), list):
        raise CanbosoCatalogError()
    products = [_normalize_product(item) for item in payload["products"]]
    wallet_currency = payload.get("walletCurrency")
    if wallet_currency is not None and (not isinstance(wallet_currency, str) or not re.fullmatch(r"[A-Za-z]{3}", wallet_currency)):
        wallet_currency = None
    return {
        "mode": "supplier",
        "is_demo": False,
        "source": "Canboso Buyer API",
        "currency": wallet_currency.upper() if wallet_currency else None,
        "products": products,
    }


class CanbosoCatalogProvider:
    """Small per-process TTL cache to stay below the supplier's rate limits."""

    def __init__(self, api_key: str, *, fetcher=None, cache_ttl: int = 20, clock=None):
        self._api_key = api_key
        self._fetcher = fetcher or fetch_canboso_catalog
        self._cache_ttl = max(0, cache_ttl)
        self._clock = clock or time.monotonic
        self._expires_at = 0.0
        self._catalog: dict | None = None
        self._lock = threading.Lock()

    def list_products(self) -> dict:
        with self._lock:
            now = self._clock()
            if self._catalog is not None and now < self._expires_at:
                return copy.deepcopy(self._catalog)
            catalog = self._fetcher(self._api_key)
            self._catalog = catalog
            self._expires_at = now + self._cache_ttl
            return copy.deepcopy(catalog)
