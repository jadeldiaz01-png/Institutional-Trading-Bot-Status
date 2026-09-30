from __future__ import annotations

import copy
import unittest
from datetime import datetime, timedelta, timezone

from edge_lab.ablation import evaluate_models
from edge_lab.feature_pipeline import build_point_in_time_panel, readiness_report


def make_bars(symbol: str, n: int = 40, start: datetime | None = None, slope: float = 1.0):
    start = start or datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(n):
        open_ts = start + timedelta(hours=i)
        close_ts = open_ts + timedelta(hours=1) - timedelta(milliseconds=1)
        close = 100.0 + slope * i
        rows.append({
            "symbol": symbol,
            "open_time_ms": int(open_ts.timestamp() * 1000),
            "close_time_ms": int(close_ts.timestamp() * 1000),
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1000.0 + i,
            "quote_volume": close * (1000.0 + i),
            "count": 100,
            "taker_buy_volume": 520.0 + i / 10.0,
            "taker_buy_quote_volume": 0.0,
            "source_path": "synthetic",
        })
    return rows


def small_protocol():
    return {
        "experiment_id": "TEST",
        "authority": {
            "edge_verified": False,
            "holdout_access": "FORBIDDEN",
            "paper_authorized": False,
            "testnet_authorized": False,
            "live_authorized": False,
        },
        "walk_forward": {
            "min_train_rows": 6,
            "test_rows": 4,
            "step_rows": 4,
            "purge_rows": 1,
            "embargo_rows": 1,
        },
        "signal": {"entry_threshold": 0.20, "feature_clip_abs_z": 3.0},
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
        "feature_sets": {"M0": ["momentum_1h"]},
    }


class PointInTimeFeatureTests(unittest.TestCase):
    def test_panel_is_multi_asset_and_cross_crypto_is_real(self):
        panel = build_point_in_time_panel({
            "BTCUSDT": make_bars("BTCUSDT", slope=1.0),
            "ETHUSDT": make_bars("ETHUSDT", slope=0.5),
        })
        assets = {row["asset"] for row in panel}
        self.assertEqual(assets, {"BTCUSDT", "ETHUSDT"})
        later = [row for row in panel if row["cross_crypto_leadlag"] is not None]
        self.assertTrue(later)

    def test_future_label_does_not_change_same_timestamp_features(self):
        spot = {
            "BTCUSDT": make_bars("BTCUSDT", slope=1.0),
            "ETHUSDT": make_bars("ETHUSDT", slope=0.5),
        }
        base = build_point_in_time_panel(copy.deepcopy(spot))
        target = next(row for row in base if row["asset"] == "BTCUSDT" and row["momentum_1h"] is not None)
        timestamp = target["timestamp"]

        changed = copy.deepcopy(spot)
        btc_rows = changed["BTCUSDT"]
        idx = next(i for i, row in enumerate(btc_rows) if row["close_time_ms"] == target["decision_time_ms"])
        btc_rows[idx + 1]["close"] *= 1.5
        altered = build_point_in_time_panel(changed)
        altered_row = next(row for row in altered if row["asset"] == "BTCUSDT" and row["timestamp"] == timestamp)

        for feature in ("momentum_1h", "momentum_4h", "momentum_1d", "order_flow_imbalance", "regime_trend", "regime_volatility"):
            self.assertEqual(target[feature], altered_row[feature], feature)
        self.assertNotEqual(target["forward_return"], altered_row["forward_return"])

    def test_onchain_is_delayed_until_day_end(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        onchain = {
            "btc": [{
                "metric_time_ms": int(start.timestamp() * 1000),
                "available_time_ms": int((start + timedelta(days=1)).timestamp() * 1000),
                "AdrActCnt": 100.0,
                "TxCnt": 200.0,
                "FeeTotNtv": 2.0,
                "source_path": "synthetic",
            }]
        }
        panel = build_point_in_time_panel(
            {"BTCUSDT": make_bars("BTCUSDT", n=50, start=start)},
            onchain=onchain,
        )
        before = [r for r in panel if r["decision_time_ms"] < onchain["btc"][0]["available_time_ms"]]
        after = [r for r in panel if r["decision_time_ms"] >= onchain["btc"][0]["available_time_ms"]]
        self.assertTrue(before)
        self.assertTrue(after)
        self.assertTrue(all(r["onchain_activity_z"] is None for r in before))
        self.assertTrue(any(r["onchain_activity_z"] is not None for r in after))

    def test_panel_benchmark_is_compounded_once_per_timestamp(self):
        rows = []
        for i in range(20):
            ts = f"2026-01-{i + 1:02d}T00:00:00Z"
            for asset in ("BTCUSDT", "ETHUSDT"):
                rows.append({
                    "timestamp": ts,
                    "asset": asset,
                    "forward_return": 0.002,
                    "benchmark_return": 0.01,
                    "momentum_1h": 2.0,
                })
        report = evaluate_models(rows, small_protocol())
        observations = report["models"]["M0"]["overall"]["observations"]
        expected = (1.01 ** observations) - 1.0
        self.assertAlmostEqual(report["models"]["M0"]["overall"]["benchmark_return"], expected, places=12)
        self.assertEqual(report["panel"]["asset_count"], 2)

    def test_readiness_uses_decision_timestamps_not_panel_rows(self):
        protocol = small_protocol()
        protocol["walk_forward"]["min_train_rows"] = 240
        protocol["walk_forward"]["test_rows"] = 72
        protocol["walk_forward"]["purge_rows"] = 1
        rows = []
        for i in range(100):
            for asset in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
                rows.append({"timestamp": f"{i:04d}", "asset": asset, "momentum_1h": 1.0})
        report = readiness_report(rows, protocol)
        self.assertEqual(report["decision_timestamps"], 100)
        self.assertEqual(report["asset_count"], 3)
        self.assertEqual(report["minimum_timestamps_for_first_fold"], 313)
        self.assertFalse(report["history_ready_for_first_fold"])
        self.assertEqual(report["decision"], "ACCUMULATE_MORE_PROSPECTIVE_DATA")

    def test_readiness_fails_closed_on_hourly_gap(self):
        protocol = small_protocol()
        protocol["walk_forward"]["min_train_rows"] = 2
        protocol["walk_forward"]["test_rows"] = 1
        protocol["walk_forward"]["purge_rows"] = 0
        rows = [
            {
                "timestamp": "2026-01-01T00:59:59.999000Z",
                "target_close_time": "2026-01-01T01:59:59.999000Z",
                "asset": "BTCUSDT",
                "momentum_1h": 1.0,
            },
            {
                "timestamp": "2026-01-01T01:59:59.999000Z",
                "target_close_time": "2026-01-01T02:59:59.999000Z",
                "asset": "BTCUSDT",
                "momentum_1h": 1.0,
            },
            {
                "timestamp": "2026-01-01T03:59:59.999000Z",
                "target_close_time": "2026-01-01T04:59:59.999000Z",
                "asset": "BTCUSDT",
                "momentum_1h": 1.0,
            },
        ]
        report = readiness_report(rows, protocol)
        self.assertEqual(report["decision_timestamps"], 3)
        self.assertFalse(report["data_quality"]["hourly_continuity_ok"])
        self.assertEqual(report["data_quality"]["max_gap_hours"], 2.0)
        self.assertFalse(report["history_ready_for_first_fold"])
        self.assertEqual(report["decision"], "ACCUMULATE_MORE_PROSPECTIVE_DATA")


if __name__ == "__main__":
    unittest.main()
