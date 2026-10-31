from __future__ import annotations

import hmac
import json
import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from canboso_catalog import CanbosoCatalogError, CanbosoCatalogProvider
from postgres_store import PostgresOrderStore
from store_app import MAX_REQUEST_BYTES, dashboard_summary, load_catalog

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
security = HTTPBasic(auto_error=False)
MIN_ADMIN_PASSWORD_LENGTH = 16


def create_app(order_store=None, settings: dict[str, str] | None = None) -> FastAPI:
    config = dict(os.environ) if settings is None else dict(settings)
    database_url = config.get("DATABASE_URL", "").strip()
    demo_checkout_enabled = config.get("DEMO_CHECKOUT_ENABLED", "").strip().lower() == "true"
    supplier_key = config.get("CANBOSO_BUYER_KEY", "").strip()
    catalog_provider = CanbosoCatalogProvider(supplier_key) if supplier_key else None
    store = order_store if order_store is not None else (PostgresOrderStore(database_url) if database_url else None)
    app = FastAPI(title="Nova Assinaturas", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.order_store = store

    @app.middleware("http")
    async def protect_private_response_caching(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path == "/admin" or path.startswith("/api/admin/") or path == "/api/products":
            response.headers["Cache-Control"] = "no-store"
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        if path in {"/", "/admin"}:
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def require_admin(credentials: HTTPBasicCredentials | None = Depends(security)) -> str:
        username = config.get("ADMIN_USER", "")
        password = config.get("ADMIN_PASSWORD", "")
        if not username or len(password) < MIN_ADMIN_PASSWORD_LENGTH:
            raise HTTPException(
                status_code=503,
                detail=f"Painel indisponível: configure ADMIN_USER e ADMIN_PASSWORD com pelo menos {MIN_ADMIN_PASSWORD_LENGTH} caracteres no Vercel.",
            )
        if credentials is None:
            raise HTTPException(
                status_code=401,
                detail="Autenticação necessária.",
                headers={"WWW-Authenticate": 'Basic realm="Nova Assinaturas Admin", charset="UTF-8"'},
            )
        valid_user = hmac.compare_digest(credentials.username.encode(), username.encode())
        valid_password = hmac.compare_digest(credentials.password.encode(), password.encode())
        if not (valid_user and valid_password):
            raise HTTPException(
                status_code=401,
                detail="Credenciais inválidas.",
                headers={"WWW-Authenticate": 'Basic realm="Nova Assinaturas Admin", charset="UTF-8"'},
            )
        return credentials.username

    @app.get("/", include_in_schema=False)
    def storefront():
        return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    @app.get("/admin", include_in_schema=False)
    def admin_page(_: str = Depends(require_admin)):
        return FileResponse(WEB_DIR / "admin.html", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    @app.get("/{asset_name}", include_in_schema=False)
    def asset(asset_name: str):
        allowed = {
            "app.css": "text/css",
            "store.js": "text/javascript",
            "admin.js": "text/javascript",
        }
        if asset_name not in allowed:
            raise HTTPException(status_code=404, detail="Rota não encontrada.")
        return FileResponse(
            WEB_DIR / asset_name,
            media_type=allowed[asset_name],
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @app.get("/api/health")
    def health():
        return {
            "ok": True,
            "mode": "demo",
            "database_configured": bool(database_url),
            "demo_checkout_enabled": demo_checkout_enabled,
            "admin_auth_configured": bool(
                config.get("ADMIN_USER") and len(config.get("ADMIN_PASSWORD", "")) >= MIN_ADMIN_PASSWORD_LENGTH
            ),
            "supplier_connected": False,
            "supplier_catalog_configured": catalog_provider is not None,
            "payments_enabled": False,
        }

    @app.get("/api/products")
    def products():
        if catalog_provider is None:
            return load_catalog()
        try:
            return catalog_provider.list_products()
        except CanbosoCatalogError as exc:
            headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
            return JSONResponse(
                {"error": str(exc)},
                status_code=exc.status_code,
                headers=headers,
            )

    @app.get("/api/admin/orders")
    def admin_orders(_: str = Depends(require_admin)):
        if store is None:
            raise HTTPException(status_code=503, detail="Configure DATABASE_URL para habilitar pedidos persistentes.")
        try:
            return {"mode": "demo", "orders": store.list_demo_orders()}
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Banco indisponível; confira DATABASE_URL.") from exc

    @app.get("/api/admin/dashboard")
    def admin_dashboard(_: str = Depends(require_admin)):
        if store is None:
            raise HTTPException(status_code=503, detail="Configure DATABASE_URL para habilitar o painel.")
        try:
            catalog = load_catalog()
            orders = store.list_demo_orders()
            return {"summary": dashboard_summary(catalog, orders), "products": catalog["products"]}
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Banco indisponível; confira DATABASE_URL.") from exc

    @app.post("/api/orders")
    async def create_order(request: Request):
        if not demo_checkout_enabled:
            return JSONResponse(
                {"error": "Checkout demo desativado; habilite DEMO_CHECKOUT_ENABLED=true somente para testes."},
                status_code=503,
            )
        if store is None:
            return JSONResponse(
                {"error": "Pedidos desativados: configure DATABASE_URL para usar um banco persistente."},
                status_code=503,
            )
        body = await request.body()
        if not body or len(body) > MAX_REQUEST_BYTES:
            return JSONResponse({"error": "Tamanho de pedido inválido."}, status_code=413)
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JSONResponse({"error": "JSON inválido."}, status_code=400)
        if not isinstance(payload, dict):
            return JSONResponse({"error": "Formato de pedido inválido."}, status_code=422)
        try:
            catalog = load_catalog()
            order = store.create_demo_order(payload.get("items"), payload.get("idempotency_key"), catalog["products"])
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        except Exception as exc:
            return JSONResponse({"error": "Não foi possível salvar o pedido demo; confira DATABASE_URL."}, status_code=503)
        return JSONResponse(
            {
                **order,
                "notice": "Demonstração: nenhuma cobrança, entrega ou reserva real de estoque foi feita.",
            },
            status_code=201,
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    return app


app = create_app()
