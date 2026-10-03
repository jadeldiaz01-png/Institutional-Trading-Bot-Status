"""Durable SQLite storage for governed Binance order state."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .contracts import OrderApproval, OrderRecord, OrderState, TradeIntent


class DuplicateOrderError(RuntimeError):
    pass


class OrderNotFoundError(KeyError):
    pass


class OrderStore:
    def __init__(self, db_path: Path):
        self._connection = sqlite3.connect(str(db_path))
        self._connection.row_factory = sqlite3.Row
        migration = Path(__file__).resolve().parents[2] / "migrations" / "001_binance_mcp_orders.sql"
        self._connection.executescript(migration.read_text(encoding="utf-8"))
        self._connection.commit()

    @property
    def connection(self) -> sqlite3.Connection:
        return self._connection

    def close(self) -> None:
        self._connection.close()

    @staticmethod
    def _to_record(row: sqlite3.Row) -> OrderRecord:
        return OrderRecord(
            order_id=row["order_id"],
            intent_sha256=row["intent_sha256"],
            idempotency_key=row["idempotency_key"],
            client_order_id=row["client_order_id"],
            state=OrderState(row["state"]),
            authorization_id=row["authorization_id"],
            reconciliation_id=row["reconciliation_id"],
        )

    def reserve(self, intent: TradeIntent, approval: OrderApproval) -> OrderRecord:
        digest = intent.intent_sha256()
        if approval.intent_sha256 != digest:
            raise ValueError("approval does not bind requested intent")
        record = OrderRecord(
            order_id=f"ord-{digest[:24]}",
            intent_sha256=digest,
            idempotency_key=digest,
            client_order_id=f"agia-{digest[:24]}",
            state=OrderState.PROPOSED,
        )
        self._insert(record)
        return record

    def _insert(self, record: OrderRecord) -> None:
        try:
            self._connection.execute(
                """
                INSERT INTO binance_mcp_orders(
                    order_id, intent_sha256, idempotency_key, client_order_id,
                    state, authorization_id, reconciliation_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.order_id,
                    record.intent_sha256,
                    record.idempotency_key,
                    record.client_order_id,
                    record.state.value,
                    record.authorization_id,
                    record.reconciliation_id,
                ),
            )
            self._connection.commit()
        except sqlite3.IntegrityError as exc:
            raise DuplicateOrderError("duplicate order identity") from exc

    def insert_record_for_test(
        self,
        *,
        order_id: str,
        intent_sha256: str,
        idempotency_key: str,
        client_order_id: str,
        state: OrderState,
    ) -> OrderRecord:
        record = OrderRecord(
            order_id=order_id,
            intent_sha256=intent_sha256,
            idempotency_key=idempotency_key,
            client_order_id=client_order_id,
            state=state,
        )
        self._insert(record)
        return record

    def get(self, order_id: str) -> OrderRecord:
        row = self._connection.execute(
            "SELECT * FROM binance_mcp_orders WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        if row is None:
            raise OrderNotFoundError(order_id)
        return self._to_record(row)

    def save(self, record: OrderRecord) -> OrderRecord:
        cursor = self._connection.execute(
            """
            UPDATE binance_mcp_orders
               SET state = ?, authorization_id = ?, reconciliation_id = ?
             WHERE order_id = ?
            """,
            (
                record.state.value,
                record.authorization_id,
                record.reconciliation_id,
                record.order_id,
            ),
        )
        if cursor.rowcount != 1:
            self._connection.rollback()
            raise OrderNotFoundError(record.order_id)
        self._connection.commit()
        return record


class SQLiteApprovalNonceStore:
    """Atomic one-time nonce consumption backed by SQLite uniqueness."""

    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection

    def consume(self, nonce: str) -> bool:
        if not nonce:
            return False
        try:
            self._connection.execute(
                "INSERT INTO binance_mcp_approval_nonces(nonce) VALUES (?)",
                (nonce,),
            )
            self._connection.commit()
            return True
        except sqlite3.IntegrityError:
            self._connection.rollback()
            return False
