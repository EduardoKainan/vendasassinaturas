import json
import unittest
from unittest.mock import Mock, patch

from canboso_catalog import CanbosoCatalogError, CanbosoCatalogProvider, fetch_canboso_catalog


SAMPLE_RESPONSE = {
    "success": True,
    "walletCurrency": "VND",
    "products": [
        {
            "productId": "prod-123",
            "name": "ChatGPT Plus 1 tháng",
            "description": "Conta com acesso por um mês",
            "productType": "account",
            "price": {"amount": 50000, "currency": "VND", "text": "50.000 ₫"},
            "availability": {"available": 7, "sold": 12},
            "promotions": [],
            "image": "/uploads/chatgpt.png",
            "emoji": "🤖",
        },
        {
            "productId": "slot_chatgpt_business",
            "name": "ChatGPT Business Slot",
            "productType": "slot",
            "price": {"amount": 8.5, "currency": "USD", "text": "$8.50"},
            "availability": {"available": None, "sold": 2},
            "promotions": [],
            "purchaseRequirements": {"customerEmail": True},
            "image": "https://elsewhere.example/unsafe.png",
        },
    ],
}


class CanbosoCatalogTests(unittest.TestCase):
    def test_fetch_normalizes_products_without_converting_supplier_price_or_unknown_stock(self):
        response = Mock()
        response.read.return_value = json.dumps(SAMPLE_RESPONSE).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch("canboso_catalog.urlopen", return_value=response) as opener:
            catalog = fetch_canboso_catalog("buyer-secret")

        self.assertEqual(opener.call_count, 1)
        request = opener.call_args.args[0]
        self.assertIn("key=buyer-secret", request.full_url)
        self.assertEqual(catalog["mode"], "supplier")
        self.assertFalse(catalog["is_demo"])
        self.assertEqual(catalog["products"][0]["id"], "prod-123")
        self.assertEqual(catalog["products"][0]["price_amount"], 50000)
        self.assertEqual(catalog["products"][0]["price_currency"], "VND")
        self.assertEqual(catalog["products"][0]["stock"], 7)
        self.assertEqual(catalog["products"][0]["cover_image"], "https://canboso.com/uploads/chatgpt.png")
        self.assertEqual(catalog["products"][0]["emoji"], "🤖")
        self.assertIsNone(catalog["products"][1]["cover_image"])
        self.assertIsNone(catalog["products"][1]["stock"])
        self.assertNotIn("buyer-secret", json.dumps(catalog))

    def test_provider_caches_catalog_to_reduce_supplier_rate_limit_pressure(self):
        fetcher = Mock(return_value={"mode": "supplier", "is_demo": False, "products": []})
        clock = Mock(side_effect=[100.0, 105.0, 121.0])
        provider = CanbosoCatalogProvider("key", fetcher=fetcher, cache_ttl=20, clock=clock)

        first = provider.list_products()
        second = provider.list_products()
        self.assertIsNot(first, second)
        self.assertEqual(fetcher.call_count, 1)
        self.assertEqual(first, second)
        provider.list_products()
        self.assertEqual(fetcher.call_count, 2)

    def test_supplier_error_is_safe_and_does_not_include_api_key(self):
        response = Mock()
        response.read.return_value = json.dumps({"success": False, "message": "Invalid API key"}).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch("canboso_catalog.urlopen", return_value=response):
            with self.assertRaises(CanbosoCatalogError) as raised:
                fetch_canboso_catalog("secret-key")
        self.assertNotIn("secret-key", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
