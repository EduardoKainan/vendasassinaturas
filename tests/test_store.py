import tempfile
import unittest
from pathlib import Path

from store_app import create_demo_order, load_catalog, validate_order_items


class StoreBusinessTests(unittest.TestCase):
    def test_catalog_is_explicitly_demo_and_exposes_product_stock(self):
        catalog = load_catalog()
        self.assertEqual(catalog["mode"], "demo")
        self.assertTrue(catalog["is_demo"])
        self.assertGreater(len(catalog["products"]), 0)
        self.assertTrue(all("stock" in product for product in catalog["products"]))

    def test_order_items_reject_quantity_above_available_stock(self):
        catalog = load_catalog()
        product = next(product for product in catalog["products"] if 0 < product["stock"] < 20)
        with self.assertRaisesRegex(ValueError, "estoque"):
            validate_order_items(
                [{"product_id": product["id"], "quantity": product["stock"] + 1}],
                catalog["products"],
            )

    def test_demo_order_persists_total_without_real_fulfillment_and_is_idempotent(self):
        catalog = load_catalog()
        product = catalog["products"][0]
        items = [{"product_id": product["id"], "quantity": 2}]
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "orders.sqlite3"
            first = create_demo_order(items, "retry-key-001", catalog["products"], db_path)
            replay = create_demo_order(items, "retry-key-001", catalog["products"], db_path)
        self.assertEqual(first["id"], replay["id"])
        self.assertEqual(first["total_cents"], product["price_cents"] * 2)
        self.assertEqual(first["status"], "demo_pending")
        self.assertFalse(first["fulfilled"])
        self.assertEqual(first["items"][0]["quantity"], 2)


if __name__ == "__main__":
    unittest.main()
