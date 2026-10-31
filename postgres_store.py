from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from store_app import validate_order_items


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS demo_orders (
    id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    items_json JSONB NOT NULL,
    total_cents BIGINT NOT NULL
)
"""


class PostgresOrderStore:
    """Persistent storage for demo orders; requires an external PostgreSQL URL."""

    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("DATABASE_URL is required.")
        self.database_url = database_url

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(
            self.database_url,
            connect_timeout=5,
            prepare_threshold=None,
            row_factory=dict_row,
        )

    @staticmethod
    def _to_order(row: dict[str, Any]) -> dict:
        created_at = row["created_at"]
        if isinstance(created_at, datetime):
            created_at = created_at.isoformat(timespec="seconds").replace("+00:00", "Z")
        items = row["items_json"]
        if isinstance(items, str):
            items = json.loads(items)
        return {
            "id": row["id"],
            "created_at": created_at,
            "status": row["status"],
            "items": items,
            "total_cents": row["total_cents"],
            "fulfilled": False,
            "mode": "demo",
        }

    def create_demo_order(self, items: object, idempotency_key: str, products: list[dict]) -> dict:
        normalized, total_cents = validate_order_items(items, products)
        if not isinstance(idempotency_key, str) or not 8 <= len(idempotency_key) <= 128:
            raise ValueError("Chave de pedido inválida.")
        order_id = "DEMO-" + uuid.uuid4().hex[:8].upper()
        now = datetime.now(timezone.utc)
        from psycopg.types.json import Jsonb

        with self._connect() as connection:
            connection.execute(SCHEMA_SQL)
            row = connection.execute(
                """INSERT INTO demo_orders
                   (id, idempotency_key, created_at, status, items_json, total_cents)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (idempotency_key) DO NOTHING
                   RETURNING id, created_at, status, items_json, total_cents""",
                (order_id, idempotency_key, now, "demo_pending", Jsonb(normalized), total_cents),
            ).fetchone()
            if row is None:
                row = connection.execute(
                    """SELECT id, created_at, status, items_json, total_cents
                       FROM demo_orders WHERE idempotency_key = %s""",
                    (idempotency_key,),
                ).fetchone()
        return self._to_order(row)

    def list_demo_orders(self, limit: int = 100) -> list[dict]:
        with self._connect() as connection:
            connection.execute(SCHEMA_SQL)
            rows = connection.execute(
                """SELECT id, created_at, status, items_json, total_cents
                   FROM demo_orders ORDER BY created_at DESC LIMIT %s""",
                (max(1, min(100, limit)),),
            ).fetchall()
        return [self._to_order(row) for row in rows]
