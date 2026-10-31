from __future__ import annotations

import copy
import json
import re
import threading
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Protocol


FRANKFURTER_RATE_URL = "https://api.frankfurter.dev/v2/rate/{base}/{quote}"
FX_SOURCE = "Frankfurter · taxas diárias de fontes oficiais"
CATEGORY_RULES = (
    ("ia-automacao", "IA e automação", ("chatgpt", "gemini", "claude", "grok", "codex", "copilot", "muse ai", "veo", "kling", "higgsfield", "manus", "perplexity", "cursor")),
    ("criacao-design", "Criação e design", ("canva", "capcut", "figma", "adobe", "freepik", "meitu", "elevenlabs", "autodesk", "midjourney", "wink")),
    ("produtividade", "Produtividade e escritório", ("notion", "microsoft", "office", "windows", "replit", "lovable", "n8n", "wispr", "zoom")),
    ("educacao", "Educação", ("duolingo", "quizlet", "skillshare", "kahoot")),
    ("entretenimento", "Entretenimento", ("youtube", "spotify", "netflix", "scribd", "brainfm")),
    ("seguranca", "VPN e segurança", ("nordvpn", "vpn", "kaspersky", "adguard", "hma")),
    ("contas-email", "Contas e e-mail", ("gmail", "hotmail", "email", "e-mail")),
)


class CatalogProvider(Protocol):
    """Adapter contract: return a supplier catalog with normalized product fields."""

    def list_products(self) -> dict:
        ...


class ExchangeRateProvider(Protocol):
    def get_rate(self, base: str, quote: str) -> dict:
        ...


class CatalogProviderError(Exception):
    """Safe provider-neutral error exposed by a catalog adapter."""

    def __init__(self, message: str = "Catálogo do fornecedor temporariamente indisponível.", *, status_code: int = 503, retry_after: int | None = None):
        super().__init__(message)
        self.status_code = status_code if status_code in {429, 503} else 503
        self.retry_after = retry_after if retry_after and retry_after > 0 else None


class ExchangeRateError(Exception):
    """Safe, provider-independent exchange-rate failure."""


class FrankfurterRateProvider:
    """Daily FX reference rates with a small in-process cache and no API key."""

    def __init__(self, *, cache_ttl: int = 21600, timeout: int = 5, clock=None):
        self._cache_ttl = max(0, cache_ttl)
        self._timeout = timeout
        self._clock = clock or time.monotonic
        self._cache: dict[tuple[str, str], tuple[float, dict]] = {}
        self._lock = threading.Lock()

    def get_rate(self, base: str, quote: str) -> dict:
        base = str(base).upper()
        quote = str(quote).upper()
        if not re.fullmatch(r"[A-Z]{3}", base) or not re.fullmatch(r"[A-Z]{3}", quote):
            raise ExchangeRateError("Código de moeda inválido para conversão.")
        if base == quote:
            return {"base": base, "quote": quote, "rate": Decimal("1"), "date": None}
        key = (base, quote)
        with self._lock:
            now = self._clock()
            cached = self._cache.get(key)
            if cached and now < cached[0]:
                return copy.deepcopy(cached[1])
            url = FRANKFURTER_RATE_URL.format(base=base.lower(), quote=quote.lower())
            request = Request(url, headers={"Accept": "application/json", "User-Agent": "NovaAssinaturasFX/1.0"})
            try:
                with urlopen(request, timeout=self._timeout) as response:
                    payload = json.loads(response.read())
            except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError, UnicodeDecodeError):
                raise ExchangeRateError("Não foi possível obter a taxa de câmbio agora.") from None
            if not isinstance(payload, dict) or payload.get("base") != base or payload.get("quote") != quote:
                raise ExchangeRateError("A fonte de câmbio retornou um par de moedas inválido.")
            try:
                rate = Decimal(str(payload.get("rate")))
                date = str(payload.get("date", ""))
                if not rate.is_finite() or rate <= 0:
                    raise InvalidOperation
                time.strptime(date, "%Y-%m-%d")
            except (InvalidOperation, TypeError, ValueError):
                raise ExchangeRateError("A fonte de câmbio retornou uma taxa inválida.") from None
            result = {"base": base, "quote": quote, "rate": rate, "date": date}
            self._cache[key] = (now + self._cache_ttl, result)
            return copy.deepcopy(result)


def _decimal_amount(value) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("Preço inválido no catálogo.")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Preço inválido no catálogo.") from None
    if not amount.is_finite() or amount < 0:
        raise ValueError("Preço inválido no catálogo.")
    return amount


def _slug(value: str) -> str:
    text = value.casefold().strip()
    replacements = {"á": "a", "à": "a", "ã": "a", "â": "a", "é": "e", "ê": "e", "í": "i", "ó": "o", "ô": "o", "õ": "o", "ú": "u", "ç": "c"}
    for source, target in replacements.items():
        text = text.replace(source, target)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-") or "outros"


def infer_category(product_name: str) -> tuple[str, str]:
    name = str(product_name or "").casefold()
    for key, label, keywords in CATEGORY_RULES:
        if any(keyword in name for keyword in keywords):
            return key, label
    return "outros", "Outros"


def enrich_catalog_for_storefront(catalog: dict, rate_provider: ExchangeRateProvider | None = None) -> dict:
    """Apply provider-neutral category and BRL presentation to any catalog adapter."""
    if not isinstance(catalog, dict) or catalog.get("mode") != "supplier" or not isinstance(catalog.get("products"), list):
        raise ValueError("Formato de catálogo do fornecedor inválido.")
    rates = rate_provider or FrankfurterRateProvider()
    result = copy.deepcopy(catalog)
    results_by_currency: dict[str, dict | None] = {}
    fx_rates: list[dict] = []

    for product in result["products"]:
        if not isinstance(product, dict):
            raise ValueError("Produto inválido no catálogo.")
        supplied_category = product.get("category")
        if isinstance(supplied_category, str) and supplied_category.strip():
            product["category"] = supplied_category.strip()
            product["category_key"] = _slug(product["category"])
        else:
            product["category_key"], product["category"] = infer_category(product.get("name", ""))
        product.setdefault("product_type_label", "")
        currency = str(product.get("price_currency", "")).upper()
        product["price_currency"] = currency
        try:
            amount = _decimal_amount(product.get("price_amount"))
            if currency == "BRL":
                rate_info = {"base": "BRL", "quote": "BRL", "rate": Decimal("1"), "date": None}
            elif currency in results_by_currency:
                rate_info = results_by_currency[currency]
            else:
                try:
                    rate_info = rates.get_rate(currency, "BRL")
                except Exception:
                    rate_info = None
                results_by_currency[currency] = rate_info
                if rate_info is not None:
                    fx_rates.append({
                        "base": currency,
                        "quote": "BRL",
                        "rate": str(rate_info["rate"]),
                        "date": rate_info["date"],
                    })
            if rate_info is None:
                raise ExchangeRateError("Taxa indisponível.")
            cents = int((amount * Decimal(str(rate_info["rate"])) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            product["price_brl_cents"] = cents
            product["price_conversion_status"] = "native_brl" if currency == "BRL" else "converted"
        except (ValueError, ExchangeRateError, KeyError, InvalidOperation, TypeError):
            product["price_brl_cents"] = None
            product["price_conversion_status"] = "unavailable"

    result["display_currency"] = "BRL"
    result["fx_provider"] = "Frankfurter"
    result["fx_source"] = FX_SOURCE
    result["fx_rates"] = fx_rates
    return result
