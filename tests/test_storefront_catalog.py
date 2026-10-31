import json
import unittest
from decimal import Decimal
from unittest.mock import Mock, patch

from storefront_catalog import FrankfurterRateProvider, enrich_catalog_for_storefront


class FixedRates:
    def __init__(self, rate=Decimal("5.25"), date="2026-10-31"):
        self.rate_value = rate
        self.date = date
        self.calls = []

    def get_rate(self, base, quote):
        self.calls.append((base, quote))
        return {"base": base, "quote": quote, "rate": self.rate_value, "date": self.date}


class StorefrontCatalogTests(unittest.TestCase):
    def test_supplier_products_are_converted_to_brl_and_categories_are_provider_neutral(self):
        rates = FixedRates()
        catalog = {
            "mode": "supplier", "is_demo": False, "source": "Example Supplier",
            "products": [
                {"id": "ai-1", "name": "ChatGPT Plus", "product_type": "account", "price_amount": 2, "price_currency": "USD", "stock": 4},
                {"id": "design-1", "name": "Canva Pro", "product_type": "slot", "price_amount": 10.01, "price_currency": "BRL", "stock": None, "category": "Criação"},
            ],
        }
        enriched = enrich_catalog_for_storefront(catalog, rates)

        self.assertEqual(enriched["display_currency"], "BRL")
        self.assertEqual(enriched["fx_provider"], "Frankfurter")
        self.assertEqual(enriched["fx_rates"][0]["date"], "2026-10-31")
        self.assertEqual(enriched["products"][0]["price_brl_cents"], 1050)
        self.assertEqual(enriched["products"][0]["category"], "IA e automação")
        self.assertEqual(enriched["products"][1]["price_brl_cents"], 1001)
        self.assertEqual(enriched["products"][1]["category"], "Criação")
        self.assertEqual(enriched["products"][1]["stock"], None)
        self.assertEqual(rates.calls, [("USD", "BRL")])

    def test_brl_amount_is_rounded_to_the_nearest_cent_without_network_call(self):
        rates = FixedRates()
        catalog = {"mode": "supplier", "is_demo": False, "products": [
            {"id": "brl", "name": "Produto em BRL", "price_amount": "10.015", "price_currency": "BRL", "stock": 1}
        ]}
        result = enrich_catalog_for_storefront(catalog, rates)
        self.assertEqual(result["products"][0]["price_brl_cents"], 1002)
        self.assertEqual(result["products"][0]["price_conversion_status"], "native_brl")
        self.assertEqual(result["fx_rates"], [])
        self.assertEqual(rates.calls, [])

    def test_missing_exchange_rate_never_falls_back_to_a_false_brl_price(self):
        class BrokenRates:
            def get_rate(self, base, quote):
                raise RuntimeError("upstream unavailable")
        catalog = {"mode": "supplier", "is_demo": False, "products": [
            {"id": "x", "name": "Unknown", "price_amount": 5, "price_currency": "USD", "stock": 1}
        ]}
        result = enrich_catalog_for_storefront(catalog, BrokenRates())
        self.assertIsNone(result["products"][0]["price_brl_cents"])
        self.assertEqual(result["products"][0]["price_conversion_status"], "unavailable")

    def test_frankfurter_rate_is_validated_and_cached(self):
        response = Mock()
        response.read.return_value = json.dumps({"date": "2026-10-31", "base": "USD", "quote": "BRL", "rate": 5.3962}).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch("storefront_catalog.urlopen", return_value=response) as opener:
            rates = FrankfurterRateProvider(cache_ttl=3600, clock=Mock(return_value=100.0))
            first = rates.get_rate("usd", "brl")
            second = rates.get_rate("USD", "BRL")
        self.assertEqual(first["rate"], Decimal("5.3962"))
        self.assertEqual(first["date"], "2026-10-31")
        self.assertEqual(first, second)
        self.assertEqual(opener.call_count, 1)
        self.assertEqual(opener.call_args.args[0].full_url, "https://api.frankfurter.dev/v2/rate/usd/brl")


if __name__ == "__main__":
    unittest.main()
