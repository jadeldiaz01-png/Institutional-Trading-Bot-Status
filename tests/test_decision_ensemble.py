from __future__ import annotations

import unittest
from dataclasses import replace

from binance_mcp.contracts import ModelDecision
from binance_mcp.decision import DecisionBundle, adjudicate


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def decision(provider: str, action: str, *, snapshot=SHA_A, freshness=100) -> ModelDecision:
    return ModelDecision(
        model_provider=provider,
        model_id=f"{provider}/model",
        model_version="v1",
        request_id=f"{provider}-request",
        timestamp_ms=1_800_000_000_000,
        symbol="BTCUSDT",
        horizon="4h",
        action=action,
        confidence=0.7,
        rationale_summary="bounded assessment",
        evidence_refs=("market:1",),
        assumptions=(),
        invalidation_conditions=(),
        risk_factors=("uncertainty",),
        uncertainty=0.3,
        data_freshness_ms=freshness,
        input_snapshot_sha256=snapshot,
    )


def bundle(chat_action="BUY", nemotron_action="BUY") -> DecisionBundle:
    return DecisionBundle(
        chatgpt=decision("openai", chat_action),
        nemotron=decision("nvidia", nemotron_action),
        market_sha256=SHA_A,
        evidence_sha256=SHA_B,
    )


class DecisionEnsembleTests(unittest.TestCase):
    def test_matching_buy_or_sell_is_candidate_not_authorization(self):
        for action in ("BUY", "SELL"):
            result = adjudicate(bundle(action, action), now_ms=1_800_000_000_200, max_age_ms=1000)
            self.assertEqual(result.action, action)
            self.assertEqual(result.status, "CANDIDATE")
            self.assertFalse(result.execution_authorized)

    def test_buy_sell_disagreement_is_no_trade_human_review(self):
        result = adjudicate(bundle("BUY", "SELL"), now_ms=1_800_000_000_200, max_age_ms=1000)
        self.assertEqual(result.action, "NO_TRADE")
        self.assertEqual(result.status, "HUMAN_REVIEW")
        self.assertFalse(result.execution_authorized)

    def test_nonmatching_hold_buy_is_no_trade_human_review(self):
        result = adjudicate(bundle("HOLD", "BUY"), now_ms=1_800_000_000_200, max_age_ms=1000)
        self.assertEqual(result.action, "NO_TRADE")
        self.assertEqual(result.status, "HUMAN_REVIEW")

    def test_any_model_no_trade_is_authoritative_for_ensemble(self):
        result = adjudicate(bundle("BUY", "NO_TRADE"), now_ms=1_800_000_000_200, max_age_ms=1000)
        self.assertEqual(result.action, "NO_TRADE")
        self.assertEqual(result.status, "BLOCKED")

    def test_stale_model_input_is_no_trade(self):
        stale = DecisionBundle(
            chatgpt=decision("openai", "BUY", freshness=5000),
            nemotron=decision("nvidia", "BUY", freshness=100),
            market_sha256=SHA_A,
            evidence_sha256=SHA_B,
        )
        result = adjudicate(stale, now_ms=1_800_000_000_200, max_age_ms=1000)
        self.assertEqual(result.action, "NO_TRADE")
        self.assertEqual(result.status, "STALE")

    def test_input_snapshot_mismatch_is_no_trade(self):
        mismatched = DecisionBundle(
            chatgpt=decision("openai", "BUY", snapshot=SHA_A),
            nemotron=decision("nvidia", "BUY", snapshot=SHA_C),
            market_sha256=SHA_A,
            evidence_sha256=SHA_B,
        )
        result = adjudicate(mismatched, now_ms=1_800_000_000_200, max_age_ms=1000)
        self.assertEqual(result.action, "NO_TRADE")
        self.assertEqual(result.status, "PROVENANCE_MISMATCH")

    def test_market_hash_must_match_model_snapshot(self):
        mismatched = replace(bundle(), market_sha256=SHA_C)
        result = adjudicate(mismatched, now_ms=1_800_000_000_200, max_age_ms=1000)
        self.assertEqual(result.action, "NO_TRADE")
        self.assertEqual(result.status, "PROVENANCE_MISMATCH")

    def test_missing_or_invalid_provenance_hash_is_rejected_at_contract_boundary(self):
        with self.assertRaises(ValueError):
            replace(bundle(), evidence_sha256="")

    def test_invalid_clock_or_max_age_fails_closed(self):
        with self.assertRaises(ValueError):
            adjudicate(bundle(), now_ms=-1, max_age_ms=1000)
        with self.assertRaises(ValueError):
            adjudicate(bundle(), now_ms=1_800_000_000_200, max_age_ms=0)


if __name__ == "__main__":
    unittest.main()
