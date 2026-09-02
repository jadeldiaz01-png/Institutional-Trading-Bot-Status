import numpy as np
import pandas as pd

from ar_tf.core import ResearchConfig
from ar_tf.research_runner import build_daily_targets


def _frame(symbol: str, quote_volume: float, periods: int = 760) -> pd.DataFrame:
    idx = pd.date_range("2023-01-01", periods=periods, freq="D", tz="UTC")
    trend = np.exp(np.linspace(0.0, 1.0, periods)) * 100.0
    return pd.DataFrame(
        {
            "symbol": symbol,
            "open": trend * 0.995,
            "high": trend * 1.01,
            "low": trend * 0.99,
            "close": trend,
            "volume": np.full(periods, quote_volume / 100.0),
            "quote_volume": np.full(periods, quote_volume),
        },
        index=idx,
    )


def test_liquidity_top_n_is_applied_point_in_time():
    frames = {
        "AAAUSDT__E01": _frame("AAAUSDT", 30_000_000.0),
        "BBBUSDT__E01": _frame("BBBUSDT", 20_000_000.0),
        "CCCUSDT__E01": _frame("CCCUSDT", 5_000_000.0),
    }
    universe = {
        "max_assets": 1,
        "min_history_days": 540,
        "liquidity_lookback_days": 30,
        "min_median_daily_notional_usd": 10_000_000.0,
        "exclude_patterns": [],
        "exclude_base_assets": [],
    }
    _, weights = build_daily_targets(frames, ResearchConfig(max_asset_weight=1.0), universe)
    mature = weights.iloc[-50:]
    assert (mature["BBBUSDT__E01"] == 0.0).all()
    assert (mature["CCCUSDT__E01"] == 0.0).all()
    assert (mature["AAAUSDT__E01"] >= 0.0).all()


def test_future_liquidity_does_not_change_past_targets():
    frames = {
        "AAAUSDT__E01": _frame("AAAUSDT", 30_000_000.0),
        "BBBUSDT__E01": _frame("BBBUSDT", 20_000_000.0),
    }
    universe = {
        "max_assets": 1,
        "min_history_days": 540,
        "liquidity_lookback_days": 30,
        "min_median_daily_notional_usd": 1_000_000.0,
        "exclude_patterns": [],
        "exclude_base_assets": [],
    }
    _, base = build_daily_targets(frames, ResearchConfig(max_asset_weight=1.0), universe)
    altered = {k: v.copy() for k, v in frames.items()}
    altered["BBBUSDT__E01"].iloc[-1, altered["BBBUSDT__E01"].columns.get_loc("quote_volume")] = 10_000_000_000.0
    _, changed = build_daily_targets(altered, ResearchConfig(max_asset_weight=1.0), universe)
    pd.testing.assert_frame_equal(base.iloc[:-1], changed.iloc[:-1])


def test_stablecoin_base_can_be_excluded():
    frames = {
        "BTCUSDT__E01": _frame("BTCUSDT", 20_000_000.0),
        "USDCUSDT__E01": _frame("USDCUSDT", 100_000_000.0),
    }
    universe = {
        "max_assets": 2,
        "min_history_days": 540,
        "liquidity_lookback_days": 30,
        "min_median_daily_notional_usd": 1_000_000.0,
        "exclude_patterns": [],
        "exclude_base_assets": ["USDC"],
    }
    _, weights = build_daily_targets(frames, ResearchConfig(max_asset_weight=1.0), universe)
    assert (weights["USDCUSDT__E01"] == 0.0).all()
