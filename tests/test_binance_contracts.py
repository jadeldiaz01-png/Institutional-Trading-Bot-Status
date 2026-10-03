from __future__ import annotations

import unittest
from dataclasses import replace

from binance_mcp.canonical import canonical_json, sha256_json
from binance_mcp.contracts import (
    ModelDecision,
    BinancePermissions,
    MarketSnapshot,
    RiskDecision,
    TradeIntent,
    OrderApproval,
    OrderState,
    OrderRecord,
)

SHA256_A = "a" * 64
SHA256_B = "b" * 64
SHA256_C = "c" * 64
SHA256_D = "d" * 64


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
        risk_snapshot_sha256=SHA256_A,
        model_bundle_sha256=SHA256_B,
        market_snapshot_sha256=SHA256_C,
        exchange_info_sha256=SHA256_D,
        created_at_ms=1_800_000_000_000,
        expires_at_ms=1_800_000_060_000,
    )


class BinanceContractTests(unittest.TestCase):
    def test_canonical_hash_is_stable_for_equivalent_mapping_order(self) -> None:
        left = {"symbol": "BTCUSDT", "nested": {"b": 2, "a": 1}}
        right = {"nested": {"a": 1, "b": 2}, "symbol": "BTCUSDT"}
        self.assertEqual(canonical_json(left), canonical_json(right))
        self.assertEqual(sha256_json(left), sha256_json(right))
        self.assertEqual(len(sha256_json(left)), 64)

    def test_trade_intent_hash_changes_when_bound_order_field_changes(self) -> None:
        base = intent()
        self.assertEqual(base.intent_sha256(), base.intent_sha256())
        changed = replace(base, quantity="0.002")
        self.assertNotEqual(base.intent_sha256(), changed.intent_sha256())

    def test_trade_intent_rejects_non_positive_quantity_and_notional(self) -> None:
        with self.assertRaises(ValueError):
            replace(intent(), quantity="0")
        with self.assertRaises(ValueError):
            replace(intent(), quantity="-0.001")
        with self.assertRaises(ValueError):
            replace(intent(), max_notional="0")

    def test_order_approval_requires_nonce_and_nonexpired_window(self) -> None:
        base = intent()
        approval = OrderApproval.from_intent(
            approval_id="approval-1",
            intent=base,
            nonce="nonce-1",
            created_at_ms=base.created_at_ms,
            expires_at_ms=base.expires_at_ms,
        )
        self.assertEqual(approval.intent_sha256, base.intent_sha256())
        self.assertEqual(approval.nonce, "nonce-1")
        with self.assertRaises(ValueError):
            replace(approval, nonce="")
        with self.assertRaises(ValueError):
            replace(approval, expires_at_ms=approval.created_at_ms)

    def test_order_state_names_are_exact(self) -> None:
        self.assertEqual(
            [state.value for state in OrderState],
            [
                "PROPOSED", "VALIDATED", "RISK_APPROVED", "HUMAN_APPROVAL_PENDING",
                "HUMAN_APPROVED", "SUBMITTING", "ACKNOWLEDGED", "UNKNOWN",
                "PARTIALLY_FILLED", "FILLED", "CANCELLED", "REJECTED", "EXPIRED",
                "RECONCILED",
            ],
        )

    def test_read_permissions_default_does_not_imply_trading_or_funds_movement(self) -> None:
        permissions = BinancePermissions(read=True)
        self.assertTrue(permissions.read)
        self.assertFalse(permissions.spot_trade)
        self.assertFalse(permissions.withdrawals)
        self.assertFalse(permissions.internal_transfer)
        self.assertFalse(permissions.universal_transfer)
        self.assertFalse(permissions.margin)
        self.assertFalse(permissions.futures)

    def test_contract_types_can_represent_advisory_and_order_records(self) -> None:
        decision = ModelDecision(
            model_provider="nvidia",
            model_id="nvidia/nemotron-3-ultra-550b-a55b",
            model_version="managed",
            request_id="r1",
            timestamp_ms=1_800_000_000_000,
            symbol="BTCUSDT",
            horizon="4h",
            action="NO_TRADE",
            confidence=0.5,
            rationale_summary="insufficient evidence",
            evidence_refs=("market:1",),
            assumptions=(),
            invalidation_conditions=(),
            risk_factors=("uncertainty",),
            uncertainty=0.5,
            data_freshness_ms=100,
            input_snapshot_sha256=SHA256_A,
        )
        market = MarketSnapshot(
            symbol="BTCUSDT",
            captured_at_ms=1_800_000_000_000,
            bid="49999.00",
            ask="50001.00",
            last="50000.00",
        )
        risk = RiskDecision(allowed=False, reasons=("NO_EDGE_VERIFIED",), snapshot_sha256=SHA256_B)
        record = OrderRecord(
            order_id="o1",
            intent_sha256=intent().intent_sha256(),
            idempotency_key="idem-1",
            client_order_id="client-1",
            state=OrderState.PROPOSED,
        )
        self.assertEqual(decision.action, "NO_TRADE")
        self.assertEqual(market.symbol, "BTCUSDT")
        self.assertFalse(risk.allowed)
        self.assertEqual(record.state, OrderState.PROPOSED)


if __name__ == "__main__":
    unittest.main()
