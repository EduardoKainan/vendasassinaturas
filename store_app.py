from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
CATALOG_PATH = ROOT / "data" / "demo_products.json"
DB_PATH = ROOT / "data" / "orders-demo.sqlite3"
MAX_ORDER_ITEMS = 10
MAX_ITEM_QUANTITY = 20
MAX_REQUEST_BYTES = 16_384


class CatalogProvider(Protocol):
    def list_products(self) -> dict:
        """Return a normalized catalog and its source mode."""


class DemoCatalogProvider:
    """Local fictional products; this provider never contacts a supplier."""

    def __init__(self, path: Path = CATALOG_PATH):
        self.path = Path(path)

    def list_products(self) -> dict:
        catalog = json.loads(self.path.read_text(encoding="utf-8"))
        if catalog.get("mode") != "demo" or catalog.get("is_demo") is not True:
            raise ValueError("O catálogo local precisa estar marcado como demonstração.")
        return catalog


def load_catalog(path: Path = CATALOG_PATH) -> dict:
    return DemoCatalogProvider(path).list_products()


def validate_order_items(items: object, products: list[dict]) -> tuple[list[dict], int]:
    if not isinstance(items, list) or not items or len(items) > MAX_ORDER_ITEMS:
        raise ValueError("Informe de 1 a 10 produtos no pedido.")

    products_by_id = {product.get("id"): product for product in products}
    seen_ids: set[str] = set()
    normalized: list[dict] = []
    total_cents = 0

    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Formato de produto inválido.")
        product_id = item.get("product_id")
        quantity = item.get("quantity")
        if not isinstance(product_id, str) or product_id not in products_by_id:
            raise ValueError("Produto não encontrado no catálogo.")
        if product_id in seen_ids:
            raise ValueError("Não repita produtos; atualize a quantidade do item.")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= MAX_ITEM_QUANTITY:
            raise ValueError("A quantidade precisa ser um número inteiro entre 1 e 20.")

        product = products_by_id[product_id]
        if not product.get("active", False):
            raise ValueError("Este produto não está disponível.")
        stock = product.get("stock")
        if isinstance(stock, bool) or not isinstance(stock, int) or stock < quantity:
            raise ValueError("Quantidade maior que o estoque disponível.")
        price_cents = product.get("price_cents")
        if isinstance(price_cents, bool) or not isinstance(price_cents, int) or price_cents < 0:
            raise ValueError("Preço inválido no catálogo.")

        line_total = price_cents * quantity
        normalized.append({
            "product_id": product_id,
            "name": str(product.get("name", "Produto"))[:120],
            "quantity": quantity,
            "unit_price_cents": price_cents,
            "line_total_cents": line_total,
        })
        total_cents += line_total
        seen_ids.add(product_id)

    return normalized, total_cents


def _connect(db_path: Path | str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """CREATE TABLE IF NOT EXISTS demo_orders (
            id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL,
            items_json TEXT NOT NULL,
            total_cents INTEGER NOT NULL
        )"""
    )
    return connection


def _row_to_order(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "status": row["status"],
        "items": json.loads(row["items_json"]),
        "total_cents": row["total_cents"],
        "fulfilled": False,
        "mode": "demo",
    }


def create_demo_order(
    items: object,
    idempotency_key: str,
    products: list[dict],
    db_path: Path | str = DB_PATH,
) -> dict:
    if not isinstance(idempotency_key, str) or not 8 <= len(idempotency_key) <= 128:
        raise ValueError("Chave de pedido inválida.")
    normalized_items, total_cents = validate_order_items(items, products)
    connection = _connect(db_path)
    try:
        existing = connection.execute(
            "SELECT * FROM demo_orders WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        if existing:
            return _row_to_order(existing)
        order_id = "DEMO-" + uuid.uuid4().hex[:8].upper()
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        connection.execute(
            "INSERT INTO demo_orders (id, idempotency_key, created_at, status, items_json, total_cents) VALUES (?, ?, ?, ?, ?, ?)",
            (order_id, idempotency_key, created_at, "demo_pending", json.dumps(normalized_items), total_cents),
        )
        connection.commit()
        row = connection.execute("SELECT * FROM demo_orders WHERE id = ?", (order_id,)).fetchone()
        return _row_to_order(row)
    finally:
        connection.close()


def list_demo_orders(db_path: Path | str = DB_PATH, limit: int = 100) -> list[dict]:
    connection = _connect(db_path)
    try:
        rows = connection.execute(
            "SELECT * FROM demo_orders ORDER BY created_at DESC LIMIT ?", (max(1, min(100, limit)),)
        ).fetchall()
        return [_row_to_order(row) for row in rows]
    finally:
        connection.close()


def dashboard_summary(catalog: dict, orders: list[dict]) -> dict:
    products = catalog["products"]
    return {
        "mode": "demo",
        "product_count": len(products),
        "stock_units": sum(max(0, int(product.get("stock", 0))) for product in products),
        "order_count": len(orders),
        "pending_count": sum(order["status"] == "demo_pending" for order in orders),
        "demo_order_value_cents": sum(order["total_cents"] for order in orders),
    }


def make_handler(db_path: Path | str = DB_PATH, provider: CatalogProvider | None = None):
    catalog_provider = provider or DemoCatalogProvider()

    class StoreHandler(BaseHTTPRequestHandler):
        server_version = "SubscriptionDemo/1.0"

        def log_message(self, fmt: str, *args) -> None:
            return

        def send_json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def send_page(self, filename: str) -> None:
            page = WEB_DIR / filename
            body = page.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def send_asset(self, filename: str, content_type: str) -> None:
            body = (WEB_DIR / filename).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            try:
                assets = {
                    "/app.css": ("app.css", "text/css; charset=utf-8"),
                    "/store.js": ("store.js", "text/javascript; charset=utf-8"),
                    "/product-locale.js": ("product-locale.js", "text/javascript; charset=utf-8"),
                    "/product-translations.pt-BR.json": ("product-translations.pt-BR.json", "application/json; charset=utf-8"),
                    "/admin.js": ("admin.js", "text/javascript; charset=utf-8"),
                }
                if path in assets:
                    return self.send_asset(*assets[path])
                if path == "/":
                    return self.send_page("index.html")
                if path == "/admin":
                    return self.send_page("admin.html")
                if path == "/api/health":
                    return self.send_json({"ok": True, "mode": "demo", "supplier_connected": False, "payments_enabled": False})
                if path == "/api/products":
                    return self.send_json(catalog_provider.list_products())
                if path == "/api/admin/orders":
                    return self.send_json({"mode": "demo", "orders": list_demo_orders(db_path)})
                if path == "/api/admin/dashboard":
                    catalog = catalog_provider.list_products()
                    orders = list_demo_orders(db_path)
                    return self.send_json({"summary": dashboard_summary(catalog, orders), "products": catalog["products"]})
                self.send_json({"error": "Rota não encontrada."}, 404)
            except (OSError, ValueError, sqlite3.Error) as exc:
                self.send_json({"error": str(exc)}, 500)

        def do_POST(self) -> None:
            if urlsplit(self.path).path != "/api/orders":
                return self.send_json({"error": "Rota não encontrada."}, 404)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > MAX_REQUEST_BYTES:
                    return self.send_json({"error": "Tamanho de pedido inválido."}, 413)
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("Formato de pedido inválido.")
                catalog = catalog_provider.list_products()
                order = create_demo_order(
                    payload.get("items"), payload.get("idempotency_key"), catalog["products"], db_path
                )
                self.send_json({
                    **order,
                    "notice": "Demonstração: nenhuma cobrança, entrega ou reserva real de estoque foi feita.",
                }, 201)
            except (json.JSONDecodeError, UnicodeDecodeError):
                self.send_json({"error": "JSON inválido."}, 400)
            except ValueError as exc:
                self.send_json({"error": str(exc)}, 422)
            except (OSError, sqlite3.Error) as exc:
                self.send_json({"error": "Não foi possível salvar o pedido demo."}, 500)

    return StoreHandler


def main() -> None:
    port = int(os.environ.get("PORT", "8767"))
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler())
    print(f"Loja de demonstração em http://127.0.0.1:{port}/ (somente local)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
