import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from http.server import ThreadingHTTPServer

from store_app import make_handler


class StoreHttpFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "orders.sqlite3"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(db_path=db_path))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp_dir.cleanup()

    def test_storefront_and_assets_are_served(self):
        with urlopen(f"{self.base}/", timeout=3) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("text/html", response.headers["Content-Type"])
        for asset, expected_type in (("app.css", "text/css"), ("store.js", "javascript"), ("admin.js", "javascript")):
            with urlopen(f"{self.base}/{asset}", timeout=3) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(expected_type, response.headers["Content-Type"])

    def test_catalog_to_demo_order_appears_in_admin_panel(self):
        with urlopen(f"{self.base}/api/products", timeout=3) as response:
            catalog = json.load(response)
        self.assertEqual(catalog["mode"], "demo")
        product = catalog["products"][0]

        payload = json.dumps({
            "items": [{"product_id": product["id"], "quantity": 2}],
            "idempotency_key": "browser-flow-test-001",
        }).encode()
        request = Request(f"{self.base}/api/orders", data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=3) as response:
            order = json.load(response)

        with urlopen(f"{self.base}/api/admin/orders", timeout=3) as response:
            admin = json.load(response)
        self.assertEqual(order["status"], "demo_pending")
        self.assertFalse(order["fulfilled"])
        self.assertEqual(order["total_cents"], product["price_cents"] * 2)
        self.assertEqual(admin["orders"][0]["id"], order["id"])


if __name__ == "__main__":
    unittest.main()
