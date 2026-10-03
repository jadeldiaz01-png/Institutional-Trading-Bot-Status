from __future__ import annotations

import unittest
from dataclasses import replace

from binance_mcp.approval import ApprovalVerifier, InMemoryApprovalNonceStore
from binance_mcp.contracts import OrderApproval, TradeIntent


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


def approval(base: TradeIntent | None = None) -> OrderApproval:
    return OrderApproval.from_intent(
        approval_id="approval-1",
        intent=base or intent(),
        nonce="nonce-1",
        created_at_ms=1_800_000_000_100,
        expires_at_ms=1_800_000_030_000,
    )


class ApprovalVerifierTests(unittest.TestCase):
    def verifier(self):
        return ApprovalVerifier(InMemoryApprovalNonceStore())

    def test_exact_approval_verifies_once_and_nonce_reuse_is_denied(self):
        verifier = self.verifier()
        base = intent()
        approved = approval(base)

        first = verifier.verify(base, approved, now_ms=1_800_000_001_000)
        self.assertTrue(first.allowed)
        self.assertEqual(first.reasons, ())

        second = verifier.verify(base, approved, now_ms=1_800_000_001_001)
        self.assertFalse(second.allowed)
        self.assertIn("NONCE_ALREADY_USED", second.reasons)

    def test_expired_or_not_yet_valid_approval_is_denied_without_consuming_nonce(self):
        store = InMemoryApprovalNonceStore()
        verifier = ApprovalVerifier(store)
        base = intent()
        approved = approval(base)

        early = verifier.verify(base, approved, now_ms=approved.created_at_ms - 1)
        self.assertFalse(early.allowed)
        self.assertIn("APPROVAL_NOT_YET_VALID", early.reasons)

        expired = verifier.verify(base, approved, now_ms=approved.expires_at_ms + 1)
        self.assertFalse(expired.allowed)
        self.assertIn("APPROVAL_EXPIRED", expired.reasons)

        valid = verifier.verify(base, approved, now_ms=1_800_000_001_000)
        self.assertTrue(valid.allowed)

    def test_every_bound_order_field_mutation_is_rejected(self):
        base = intent()
        approved = approval(base)
        mutations = {
            "intent_sha256": "f" * 64,
            "account_alias": "spot-secondary",
            "environment": "LIVE_PILOT",
            "symbol": "ETHUSDT",
            "side": "SELL",
            "order_type": "MARKET",
            "quantity": "0.002",
            "price": "50001.00",
            "stop_price": "49000.00",
            "time_in_force": "IOC",
            "max_slippage_bps": "30",
            "max_notional": "110.00",
            "strategy_id": "other-strategy",
            "strategy_version": "2",
            "risk_snapshot_sha256": "e" * 64,
            "model_bundle_sha256": "e" * 64,
            "market_snapshot_sha256": "e" * 64,
            "exchange_info_sha256": "e" * 64,
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                verifier = self.verifier()
                altered = replace(approved, **{field: value})
                result = verifier.verify(base, altered, now_ms=1_800_000_001_000)
                self.assertFalse(result.allowed)
                self.assertIn("APPROVAL_INTENT_MISMATCH", result.reasons)

    def test_quote_quantity_binding_is_exact(self):
        quoted = replace(intent(), quantity=None, quote_quantity="50.00")
        approved = approval(quoted)
        verifier = self.verifier()
        valid = verifier.verify(quoted, approved, now_ms=1_800_000_001_000)
        self.assertTrue(valid.allowed)

        verifier = self.verifier()
        altered = replace(approved, quote_quantity="51.00")
        denied = verifier.verify(quoted, altered, now_ms=1_800_000_001_000)
        self.assertFalse(denied.allowed)
        self.assertIn("APPROVAL_INTENT_MISMATCH", denied.reasons)


if __name__ == "__main__":
    unittest.main()
