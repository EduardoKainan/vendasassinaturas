import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import create_app
from store_app import load_catalog


class MemoryOrderStore:
    def __init__(self):
        self.orders = []

    def create_demo_order(self, items, idempotency_key, products):
        order = {
            "id": "DEMO-TEST0001",
            "created_at": "2026-01-01T00:00:00Z",
            "status": "demo_pending",
            "items": [{"product_id": items[0]["product_id"], "name": products[0]["name"], "quantity": items[0]["quantity"], "unit_price_cents": products[0]["price_cents"], "line_total_cents": products[0]["price_cents"] * items[0]["quantity"]}],
            "total_cents": products[0]["price_cents"] * items[0]["quantity"],
            "fulfilled": False,
            "mode": "demo",
        }
        self.orders.append(order)
        return order

    def list_demo_orders(self):
        return list(reversed(self.orders))


class VercelAppTests(unittest.TestCase):
    def test_public_routes_serve_store_and_health_without_exposing_admin(self):
        with patch.dict("os.environ", {}, clear=True):
            client = TestClient(create_app(order_store=MemoryOrderStore()))
        page = client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("default-src 'self'", page.headers["content-security-policy"])
        self.assertEqual(client.get("/app.css").status_code, 200)
        health = client.get("/api/health").json()
        self.assertFalse(health["database_configured"])
        self.assertFalse(health["demo_checkout_enabled"])
        self.assertFalse(health["supplier_connected"])
        self.assertFalse(health["payments_enabled"])

    def test_public_products_uses_server_side_supplier_key_and_returns_read_only_catalog(self):
        catalog = {
            "mode": "supplier",
            "is_demo": False,
            "source": "Canboso Buyer API",
            "currency": "VND",
            "products": [{"id": "prod-1", "name": "Plan", "price_amount": 50000, "price_currency": "VND", "stock": None}],
        }
        with patch.dict("os.environ", {}, clear=True), patch("app.CanbosoCatalogProvider") as provider_class:
            provider_class.return_value.list_products.return_value = catalog
            client = TestClient(create_app(settings={"CANBOSO_BUYER_KEY": "server-only-secret"}))
            response = client.get("/api/products")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), catalog)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertNotIn("server-only-secret", response.text)
        provider_class.assert_called_once_with("server-only-secret")
        health = client.get("/api/health").json()
        self.assertTrue(health["supplier_catalog_configured"])
        self.assertNotIn("server-only-secret", str(health))

    def test_supplier_rate_limit_is_forwarded_without_leaking_credentials(self):
        from canboso_catalog import CanbosoCatalogError
        with patch.dict("os.environ", {}, clear=True), patch("app.CanbosoCatalogProvider") as provider_class:
            provider_class.return_value.list_products.side_effect = CanbosoCatalogError(status_code=429, retry_after=12)
            client = TestClient(create_app(settings={"CANBOSO_BUYER_KEY": "server-only-secret"}))
            response = client.get("/api/products")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["retry-after"], "12")
        self.assertNotIn("server-only-secret", response.text)

    def test_orders_require_persistent_database_configuration(self):
        with patch.dict("os.environ", {}, clear=True):
            client = TestClient(create_app(settings={"DEMO_CHECKOUT_ENABLED": "true"}))
        product = load_catalog()["products"][0]
        response = client.post("/api/orders", json={
            "items": [{"product_id": product["id"], "quantity": 1}],
            "idempotency_key": "vercel-test-no-db",
        })
        self.assertEqual(response.status_code, 503)
        self.assertIn("DATABASE_URL", response.json()["error"])

    def test_admin_panel_requires_configured_credentials_and_authentication(self):
        with patch.dict("os.environ", {}, clear=True):
            unconfigured = TestClient(create_app(order_store=MemoryOrderStore()))
        self.assertEqual(unconfigured.get("/admin").status_code, 503)

        with patch.dict("os.environ", {"ADMIN_USER": "operator", "ADMIN_PASSWORD": "test-secret-long-enough"}, clear=True):
            client = TestClient(create_app(order_store=MemoryOrderStore()))
            denied = client.get("/admin")
            allowed = client.get("/admin", auth=("operator", "test-secret-long-enough"))
        self.assertEqual(denied.status_code, 401)
        self.assertIn("Basic", denied.headers.get("www-authenticate", ""))
        self.assertEqual(allowed.status_code, 200)
        self.assertIn("Painel de vendas", allowed.text)

    def test_short_admin_password_is_rejected(self):
        with patch.dict("os.environ", {"ADMIN_USER": "operator", "ADMIN_PASSWORD": "short"}, clear=True):
            client = TestClient(create_app(order_store=MemoryOrderStore()))
        response = client.get("/admin")
        self.assertEqual(response.status_code, 503)
        self.assertIn("16", response.json()["detail"])

    def test_authenticated_admin_can_read_dashboard_and_orders(self):
        store = MemoryOrderStore()
        catalog = load_catalog()
        store.create_demo_order([{"product_id": catalog["products"][0]["id"], "quantity": 2}], "key", catalog["products"])
        with patch.dict("os.environ", {"ADMIN_USER": "operator", "ADMIN_PASSWORD": "test-secret-long-enough"}, clear=True):
            client = TestClient(create_app(order_store=store))
        auth = ("operator", "test-secret-long-enough")
        orders_response = client.get("/api/admin/orders", auth=auth)
        dashboard_response = client.get("/api/admin/dashboard", auth=auth)
        self.assertEqual(orders_response.json()["orders"][0]["id"], "DEMO-TEST0001")
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertEqual(orders_response.headers["cache-control"], "no-store")

    def test_public_checkout_writes_only_demo_order_through_store(self):
        store = MemoryOrderStore()
        product = load_catalog()["products"][0]
        with patch.dict("os.environ", {}, clear=True):
            client = TestClient(create_app(order_store=store, settings={"DEMO_CHECKOUT_ENABLED": "true"}))
        response = client.post("/api/orders", json={
            "items": [{"product_id": product["id"], "quantity": 2}],
            "idempotency_key": "vercel-test-order",
        })
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.json()["fulfilled"])
        self.assertIn("nenhuma cobrança", response.json()["notice"])
        self.assertEqual(len(store.orders), 1)

    def test_demo_checkout_is_closed_by_default_even_when_storage_exists(self):
        store = MemoryOrderStore()
        product = load_catalog()["products"][0]
        with patch.dict("os.environ", {}, clear=True):
            client = TestClient(create_app(order_store=store))
        response = client.post("/api/orders", json={
            "items": [{"product_id": product["id"], "quantity": 1}],
            "idempotency_key": "checkout-disabled-001",
        })
        self.assertEqual(response.status_code, 503)
        self.assertEqual(len(store.orders), 0)


if __name__ == "__main__":
    unittest.main()
