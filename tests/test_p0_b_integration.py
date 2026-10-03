from __future__ import annotations

import os
from decimal import Decimal

import psycopg
import pytest

from institutional_trading.domain import Environment, OrderIntent
from institutional_trading.opa_client import OPAClient
from institutional_trading.persistent_evidence import PersistentEvidenceLedger
from institutional_trading.repository import PostgresStore


pytestmark = pytest.mark.integration


def intent() -> OrderIntent:
    return OrderIntent(
        client_order_id="integration-order-0001",
        idempotency_key="integration-idem-0000000001",
        environment=Environment.TESTNET,
        account_ref="acct-testnet",
        strategy_id="integration",
        strategy_version="1",
        symbol="BTCUSDT",
        side="BUY",
        quantity=Decimal("0.001"),
        order_type="LIMIT",
        limit_price=Decimal("10000"),
        signal_ref="integration:signal",
    )


def require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        pytest.skip(f"{name} is not configured")
    return value


def test_postgres_schema_and_durable_intent():
    dsn = require("TESTNET_DATABASE_DSN")
    store = PostgresStore(dsn)
    item = intent()
    store.insert_intent(item)
    row = store.get_intent(item.intent_id)
    assert row is not None
    assert row["idempotency_key"] == item.idempotency_key
    assert row["state"] == "CREATED"


def test_opa_testnet_requires_verified_workload():
    opa = OPAClient(require("OPA_URL"))
    item = intent()
    allowed = opa.evaluate(
        item,
        risk_allowed=True,
        kill_switch_clear=True,
        workload_verified=True,
        audit_available=True,
        reconciliation_available=True,
    )
    denied = opa.evaluate(
        item,
        risk_allowed=True,
        kill_switch_clear=True,
        workload_verified=False,
        audit_available=True,
        reconciliation_available=True,
    )
    assert allowed.allowed is True
    assert denied.allowed is False


def test_evidence_ledger_persists_hash_chain():
    dsn = require("TESTNET_DATABASE_DSN")
    store = PostgresStore(dsn)
    ledger = PersistentEvidenceLedger(store)
    first = ledger.append(actor="ci", event_type="gate.start", subject_ref="p0-b", payload={"n": 1})
    second = ledger.append(actor="ci", event_type="gate.finish", subject_ref="p0-b", payload={"n": 2})
    assert first.verify() and second.verify()
    assert second.previous_hash == first.event_hash
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM evidence_ledger")
        assert cur.fetchone()[0] >= 2
