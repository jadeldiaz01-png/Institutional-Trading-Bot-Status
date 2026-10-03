from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from .domain import IntentState, OrderIntent


class DuplicateIntentError(RuntimeError):
    pass


@dataclass(slots=True)
class BrokerObservation:
    intent_id: UUID
    broker: str
    broker_order_id: str | None
    broker_status: str | None
    reconciliation_required: bool
    observed_at: datetime


class PostgresStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def connect(self):
        return psycopg.connect(self._dsn, row_factory=dict_row)

    def insert_intent(self, intent: OrderIntent) -> None:
        sql = """
        INSERT INTO order_intents (
          intent_id, client_order_id, idempotency_key, fingerprint, environment,
          account_ref, strategy_id, strategy_version, symbol, side, quantity,
          order_type, limit_price, signal_ref, approval_ref, policy_decision_ref,
          risk_decision_ref, state, created_at, updated_at
        ) VALUES (
          %(intent_id)s, %(client_order_id)s, %(idempotency_key)s, %(fingerprint)s,
          %(environment)s, %(account_ref)s, %(strategy_id)s, %(strategy_version)s,
          %(symbol)s, %(side)s, %(quantity)s, %(order_type)s, %(limit_price)s,
          %(signal_ref)s, %(approval_ref)s, %(policy_decision_ref)s,
          %(risk_decision_ref)s, %(state)s, %(created_at)s, now()
        )
        ON CONFLICT (idempotency_key) DO NOTHING
        """
        values = intent.model_dump(mode="python")
        values["fingerprint"] = intent.canonical_fingerprint()
        values["environment"] = intent.environment.value
        values["state"] = intent.state.value
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, values)
                if cur.rowcount != 1:
                    cur.execute(
                        "SELECT fingerprint FROM order_intents WHERE idempotency_key=%s",
                        (intent.idempotency_key,),
                    )
                    row = cur.fetchone()
                    if not row or row["fingerprint"] != values["fingerprint"]:
                        raise DuplicateIntentError("idempotency key reused with different intent")
            conn.commit()

    def transition(self, intent_id: UUID, expected: Iterable[IntentState], target: IntentState) -> bool:
        expected_values = [s.value for s in expected]
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE order_intents
                    SET state=%s, version=version+1, updated_at=now()
                    WHERE intent_id=%s AND state = ANY(%s)
                    """,
                    (target.value, intent_id, expected_values),
                )
                changed = cur.rowcount == 1
            conn.commit()
        return changed

    def get_intent(self, intent_id: UUID) -> dict | None:
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM order_intents WHERE intent_id=%s", (intent_id,))
            return cur.fetchone()

    def list_reconciliation_candidates(self, limit: int = 100) -> list[dict]:
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT oi.*, bol.broker_order_id, bol.broker_status
                FROM order_intents oi
                LEFT JOIN broker_order_links bol USING (intent_id)
                WHERE oi.state IN ('SUBMITTING','UNKNOWN','PARTIALLY_FILLED')
                ORDER BY oi.updated_at ASC
                LIMIT %s
                """,
                (limit,),
            )
            return list(cur.fetchall())

    def upsert_broker_observation(self, obs: BrokerObservation) -> None:
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO broker_order_links (
                  intent_id, broker, broker_order_id, broker_status,
                  last_observed_at, reconciliation_required
                ) VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (intent_id) DO UPDATE SET
                  broker=EXCLUDED.broker,
                  broker_order_id=EXCLUDED.broker_order_id,
                  broker_status=EXCLUDED.broker_status,
                  last_observed_at=EXCLUDED.last_observed_at,
                  reconciliation_required=EXCLUDED.reconciliation_required
                """,
                (
                    obs.intent_id, obs.broker, obs.broker_order_id, obs.broker_status,
                    obs.observed_at, obs.reconciliation_required,
                ),
            )
            conn.commit()

    def append_evidence(self, event_id: UUID, actor: str, event_type: str, subject_ref: str,
                        payload: dict, previous_hash: str | None, event_hash: str) -> None:
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO evidence_ledger (
                  event_id, occurred_at, actor, event_type, subject_ref,
                  payload_json, previous_hash, event_hash
                ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
                """,
                (
                    event_id, datetime.now(timezone.utc), actor, event_type,
                    subject_ref, json.dumps(payload, sort_keys=True), previous_hash, event_hash,
                ),
            )
            conn.commit()

    def latest_evidence_hash(self) -> str | None:
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT event_hash FROM evidence_ledger ORDER BY sequence DESC LIMIT 1")
            row = cur.fetchone()
            return row["event_hash"] if row else None
