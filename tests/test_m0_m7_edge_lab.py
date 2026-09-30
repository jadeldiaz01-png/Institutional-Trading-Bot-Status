from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from edge_lab.ablation import CostModel, evaluate_models, make_walk_forward_folds, position_from_score, score_row


PROTOCOL_PATH = Path("experiments/m0_m7_edge_search/protocol.json")


def small_protocol() -> dict:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    protocol["walk_forward"] = {
        "min_train_rows": 6,
        "test_rows": 4,
        "step_rows": 4,
        "purge_rows": 1,
        "embargo_rows": 1,
    }
    protocol["annualization_periods"] = 365
    return protocol


def synthetic_rows(n: int = 20) -> list[dict]:
    rows = []
    for i in range(n):
        direction = 1.0 if i % 6 < 4 else -1.0
        row = {
            "timestamp": f"2026-01-{i + 1:02d}T00:00:00Z",
            "forward_return": 0.006 * direction,
            "benchmark_return": 0.001,
            "funding_bps": 0.2,
            "spread_bps": 1.0,
            "slippage_bps": 0.5,
            "momentum_1h": direction * 2.0,
            "momentum_4h": direction * 1.5,
            "momentum_1d": direction,
            "cross_crypto_leadlag": direction,
            "funding_z": -direction * 0.2,
            "oi_change_z": direction,
            "basis_z": direction * 0.5,
            "taker_imbalance": direction,
            "order_flow_imbalance": direction,
            "book_imbalance": direction,
            "microprice_edge": direction,
            "onchain_activity_z": direction * 0.5,
            "exchange_netflow_z": direction * 0.3,
            "network_growth_z": direction * 0.4,
            "sentiment_z": direction,
            "news_novelty": direction * 0.2,
            "llm_event_score": direction,
            "llm_event_confidence": 0.8,
            "regime_trend": direction,
            "regime_volatility": -0.1,
        }
        rows.append(row)
    return rows


class EdgeLabTests(unittest.TestCase):
    def test_walk_forward_has_purge_and_embargo(self) -> None:
        folds = make_walk_forward_folds(
            20,
            min_train_rows=6,
            test_rows=4,
            step_rows=4,
            purge_rows=1,
            embargo_rows=2,
        )
        self.assertGreaterEqual(len(folds), 2)
        for fold in folds:
            self.assertEqual(fold["test_start"] - fold["train_end_exclusive"], 1)
            self.assertGreaterEqual(fold["embargo_end_exclusive"], fold["test_end_exclusive"])

    def test_no_trade_zone(self) -> None:
        score = score_row(
            {"momentum_1h": 0.1, "momentum_4h": -0.1},
            ["momentum_1h", "momentum_4h"],
            clip_abs_z=3.0,
        )
        self.assertEqual(position_from_score(score, entry_threshold=0.2), 0)

    def test_cost_model_penalizes_turnover(self) -> None:
        model = CostModel(taker_fee_bps=4.0, default_half_spread_bps=1.0, default_slippage_bps=2.0)
        cost0 = model.execution_cost_fraction(0.0, {})
        cost1 = model.execution_cost_fraction(1.0, {})
        cost2 = model.execution_cost_fraction(2.0, {})
        self.assertEqual(cost0, 0.0)
        self.assertGreater(cost1, 0.0)
        self.assertAlmostEqual(cost2, cost1 * 2.0)

    def test_evaluator_never_certifies_edge_or_live(self) -> None:
        report = evaluate_models(synthetic_rows(), small_protocol())
        self.assertFalse(report["EDGE_VERIFIED"])
        self.assertEqual(report["decision"], "NO_EDGE_VERIFIED")
        self.assertFalse(report["holdout_accessed"])
        self.assertFalse(report["paper_authorized"])
        self.assertFalse(report["testnet_authorized"])
        self.assertFalse(report["live_authorized"])
        self.assertEqual(set(report["models"]), {f"M{i}" for i in range(8)})

    def test_live_authority_in_protocol_fails_closed(self) -> None:
        protocol = copy.deepcopy(small_protocol())
        protocol["authority"]["live_authorized"] = True
        with self.assertRaisesRegex(ValueError, "live_authorized"):
            evaluate_models(synthetic_rows(), protocol)

    def test_missing_features_block_model_instead_of_silent_fallback(self) -> None:
        rows = synthetic_rows()
        for row in rows:
            row["momentum_1d"] = None
        report = evaluate_models(rows, small_protocol())
        m0 = report["models"]["M0"]
        self.assertEqual(m0["status"], "BLOCKED_MISSING_FEATURES")
        self.assertIn("momentum_1d", m0["missing_features"])
        self.assertFalse(m0["candidate_screen_pass"])
        self.assertIsNone(m0["overall"])
        self.assertIn("M0", report["blocked_models"])

    def test_fully_populated_model_is_evaluated(self) -> None:
        report = evaluate_models(synthetic_rows(), small_protocol())
        self.assertEqual(report["models"]["M0"]["status"], "EVALUATED_OOS")
        self.assertIn("M0", report["eligible_models"])
        self.assertNotIn("M0", report["blocked_models"])


if __name__ == "__main__":
    unittest.main()
