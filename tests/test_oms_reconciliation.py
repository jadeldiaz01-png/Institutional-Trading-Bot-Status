from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from binance_mcp.approval import ApprovalVerifier
from binance_mcp.contracts import OrderApproval, OrderState, TradeIntent
from binance_mcp.oms import DuplicateOrderError, InvalidTransition, OMS
from binance_mcp.reconcile import Reconciler
from binance_mcp.store import OrderStore, SQLiteApprovalNonceStore


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64


def intent() -> TradeIntent:
    return TradeIntent(
        account_alias="spot-primary",
        environment="TESTNET",
        symbol="BTCUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity="0.001",
        quote_quantity=None,
        price="50000.00",
        stop_price=None,
        time_in_force="GTC",
        max_slippage_bps="25",
        max_notional="100.00",
        strategy_id="manual-reviewed",
        strategy_version="1",
        risk_snapshot_sha256=SHA_A,
        model_bundle_sha256=SHA_B,
        market_snapshot_sha256=SHA_C,
        exchange_info_sha256=SHA_D,
        created_at_ms=1_800_000_000_000,
        expires_at_ms=1_800_000_060_000,
    )


def approval(base: TradeIntent | None = None, nonce="nonce-1") -> OrderApproval:
    base = base or intent()
    return OrderApproval.from_intent(
        approval_id="approval-1",
        intent=base,
        nonce=nonce,
        created_at_ms=1_800_000_000_100,
        expires_at_ms=1_800_000_030_000,
    )


class OMSReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "orders.sqlite3"
        self.store = OrderStore(self.db)
        self.oms = OMS(self.store)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def reserve(self):
        return self.store.reserve(intent(), approval())

    def test_reserve_is_unique_by_intent_idempotency_and_client_order_id(self):
        record = self.reserve()
        self.assertEqual(record.state, OrderState.PROPOSED)
        self.assertEqual(record.idempotency_key, intent().intent_sha256())
        self.assertTrue(record.client_order_id.startswith("agia-"))

        with self.assertRaises(DuplicateOrderError):
            self.store.reserve(intent(), approval(nonce="nonce-2"))

        with self.assertRaises(DuplicateOrderError):
            self.store.insert_record_for_test(
                order_id="other-order",
                intent_sha256="e" * 64,
                idempotency_key="e" * 64,
                client_order_id=record.client_order_id,
                state=OrderState.PROPOSED,
            )

    def test_illegal_state_transition_is_rejected(self):
        record = self.reserve()
        with self.assertRaises(InvalidTransition):
            self.oms.transition(record.order_id, OrderState.SUBMITTING, evidence={})

    def test_authorization_and_reconciliation_evidence_are_required(self):
        record = self.reserve()
        record = self.oms.transition(record.order_id, OrderState.VALIDATED, evidence={})
        record = self.oms.transition(record.order_id, OrderState.RISK_APPROVED, evidence={})
        record = self.oms.transition(record.order_id, OrderState.HUMAN_APPROVAL_PENDING, evidence={})
        with self.assertRaises(InvalidTransition):
            self.oms.transition(record.order_id, OrderState.HUMAN_APPROVED, evidence={})

        record = self.oms.transition(
            record.order_id,
            OrderState.HUMAN_APPROVED,
            evidence={"authorization_id": "approval-1"},
        )
        record = self.oms.transition(record.order_id, OrderState.SUBMITTING, evidence={})
        record = self.oms.transition(record.order_id, OrderState.UNKNOWN, evidence={})
        with self.assertRaises(InvalidTransition):
            self.oms.transition(record.order_id, OrderState.RECONCILED, evidence={})

    def test_ambiguous_submit_stays_unknown_until_reconciled_by_client_order_id(self):
        record = self.reserve()
        for state, evidence in [
            (OrderState.VALIDATED, {}),
            (OrderState.RISK_APPROVED, {}),
            (OrderState.HUMAN_APPROVAL_PENDING, {}),
            (OrderState.HUMAN_APPROVED, {"authorization_id": "approval-1"}),
            (OrderState.SUBMITTING, {}),
            (OrderState.UNKNOWN, {}),
        ]:
            record = self.oms.transition(record.order_id, state, evidence=evidence)

        calls = []
        reconciler = Reconciler(self.oms)
        still_unknown = reconciler.reconcile_unknown(
            record,
            exchange_lookup=lambda client_order_id: calls.append(client_order_id) or None,
            confirmed_absent=False,
        )
        self.assertEqual(calls, [record.client_order_id])
        self.assertEqual(still_unknown.state, OrderState.UNKNOWN)

        found = reconciler.reconcile_unknown(
            record,
            exchange_lookup=lambda _: {"status": "FILLED", "orderId": 123},
            confirmed_absent=False,
        )
        self.assertEqual(found.state, OrderState.RECONCILED)
        self.assertIsNotNone(found.reconciliation_id)

    def test_confirmed_final_absence_can_reconcile_without_retrying_submit(self):
        record = self.reserve()
        for state, evidence in [
            (OrderState.VALIDATED, {}),
            (OrderState.RISK_APPROVED, {}),
            (OrderState.HUMAN_APPROVAL_PENDING, {}),
            (OrderState.HUMAN_APPROVED, {"authorization_id": "approval-1"}),
            (OrderState.SUBMITTING, {}),
            (OrderState.UNKNOWN, {}),
        ]:
            record = self.oms.transition(record.order_id, state, evidence=evidence)

        reconciled = Reconciler(self.oms).reconcile_unknown(
            record,
            exchange_lookup=lambda _: None,
            confirmed_absent=True,
        )
        self.assertEqual(reconciled.state, OrderState.RECONCILED)
        self.assertTrue(reconciled.reconciliation_id.startswith("confirmed-absent:"))

    def test_durable_nonce_store_consumes_once_atomically(self):
        nonces = SQLiteApprovalNonceStore(self.store.connection)
        verifier = ApprovalVerifier(nonces)
        base = intent()
        approved = approval(base)
        first = verifier.verify(base, approved, now_ms=1_800_000_001_000)
        second = verifier.verify(base, approved, now_ms=1_800_000_001_001)
        self.assertTrue(first.allowed)
        self.assertFalse(second.allowed)
        self.assertIn("NONCE_ALREADY_USED", second.reasons)


if __name__ == "__main__":
    unittest.main()
