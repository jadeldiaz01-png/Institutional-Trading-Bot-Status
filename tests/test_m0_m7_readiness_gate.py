from __future__ import annotations

import unittest

from edge_lab.readiness_gate import evaluate_readiness_gate


def protocol() -> dict:
    return {
        "experiment_id": "READINESS-TEST",
        "authority": {
            "edge_verified": False,
            "holdout_access": "FORBIDDEN",
            "paper_authorized": False,
            "testnet_authorized": False,
            "live_authorized": False,
        },
        "walk_forward": {
            "min_train_rows": 2,
            "test_rows": 2,
            "step_rows": 2,
            "purge_rows": 0,
            "embargo_rows": 0,
        },
        "signal": {
            "entry_threshold": 0.2,
            "feature_clip_abs_z": 3.0,
        },
        "cost_model": {
            "taker_fee_bps": 0.0,
            "maker_fee_bps": 0.0,
            "default_half_spread_bps": 0.0,
            "default_slippage_bps": 0.0,
            "execution_style": "taker",
        },
        "annualization_periods": 365,
        "candidate_screen": {
            "require_net_return_positive": False,
            "require_simple_alpha_positive": False,
            "require_positive_fold_fraction": 0.0,
            "require_sharpe_positive": False,
        },
        "feature_sets": {
            "M0": ["momentum_1h"],
            "M1": ["momentum_1h", "funding_z"],
        },
    }


def rows() -> list[dict]:
    result = []
    for i in range(6):
        result.append({
            "timestamp": f"2026-01-01T0{i}:00:00Z",
            "asset": "BTCUSDT",
            "forward_return": 0.01,
            "benchmark_return": 0.0,
            "momentum_1h": 2.0,
            "funding_z": None,
            "funding_bps": 0.0,
            "spread_bps": 0.0,
            "slippage_bps": 0.0,
        })
    return result


def readiness(ready: bool) -> dict:
    return {
        "EDGE_VERIFIED": False,
        "holdout_accessed": False,
        "paper_authorized": False,
        "testnet_authorized": False,
        "live_authorized": False,
        "history_ready_for_first_fold": ready,
        "decision_timestamps": 313 if ready else 23,
        "minimum_timestamps_for_first_fold": 313,
    }


class ReadinessGateTests(unittest.TestCase):
    def test_waiting_state_never_runs_ablation(self) -> None:
        state, report = evaluate_readiness_gate(
            readiness=readiness(False),
            rows=rows(),
            protocol=protocol(),
            metadata={"run_id": "1", "run_attempt": "1", "workflow_source_sha": "a" * 40},
        )
        self.assertIsNone(report)
        self.assertEqual(state["status"], "WAITING_FOR_PROSPECTIVE_DATA")
        self.assertEqual(state["next_gate"], "CONTINUE_AUTOMATIC_ACCUMULATION")
        self.assertFalse(state["EDGE_VERIFIED"])
        self.assertFalse(state["live_authorized"])

    def test_ready_state_evaluates_complete_model_and_blocks_incomplete_model(self) -> None:
        state, report = evaluate_readiness_gate(
            readiness=readiness(True),
            rows=rows(),
            protocol=protocol(),
        )
        self.assertIsNotNone(report)
        assert report is not None
        self.assertEqual(state["status"], "RESEARCH_ABLATION_COMPLETE")
        self.assertEqual(state["next_gate"], "HUMAN_REVIEW_OF_RESEARCH_RESULTS")
        self.assertIn("M0", state["eligible_models"])
        self.assertIn("M1", state["blocked_models"])
        self.assertEqual(report["models"]["M0"]["status"], "EVALUATED_OOS")
        self.assertEqual(report["models"]["M1"]["status"], "BLOCKED_MISSING_FEATURES")
        self.assertFalse(report["EDGE_VERIFIED"])
        self.assertFalse(report["live_authorized"])

    def test_readiness_authority_fails_closed(self) -> None:
        bad = readiness(False)
        bad["live_authorized"] = True
        with self.assertRaises(AssertionError):
            evaluate_readiness_gate(
                readiness=bad,
                rows=rows(),
                protocol=protocol(),
            )


if __name__ == "__main__":
    unittest.main()
