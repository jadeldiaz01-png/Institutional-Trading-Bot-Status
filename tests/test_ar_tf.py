import numpy as np
import pandas as pd

from ar_tf.backtest import CostModel, run_backtest
from ar_tf.core import ResearchConfig, build_features, build_signal, portfolio_weights
from ar_tf.validation import (
    certification_decision,
    deflated_sharpe_probability,
    expected_max_sharpe,
    performance_metrics,
)


def sample_prices(n=500):
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    close = pd.Series(np.exp(np.linspace(0, 0.8, n)), index=idx)
    return pd.DataFrame({"close": close, "high": close * 1.01, "low": close * 0.99, "volume": 1_000_000.0}, index=idx)


def test_features_and_signal_are_causal_shapes():
    x = build_features(sample_prices())
    s = build_signal(x)
    assert s.index.equals(x.index)
    assert (s.dropna() >= 0).all()


def test_portfolio_respects_caps():
    cfg = ResearchConfig(max_asset_weight=0.15, max_gross_exposure=1.0)
    symbols = pd.Index([f"A{i}" for i in range(10)])
    w = portfolio_weights(pd.Series(1.0, index=symbols), pd.Series(0.5, index=symbols), cfg)
    assert w.max() <= 0.15 + 1e-12
    assert w.sum() <= 1.0 + 1e-12


def test_backtest_shifts_weights_and_charges_costs():
    idx = pd.date_range("2025-01-01", periods=4, freq="D", tz="UTC")
    r = pd.DataFrame({"BTCUSDT": [0.10, 0.10, 0.10, 0.10]}, index=idx)
    w = pd.DataFrame({"BTCUSDT": [1.0, 1.0, 1.0, 1.0]}, index=idx)
    result = run_backtest(r, w, CostModel(taker_fee_bps=10, half_spread_bps=0, slippage_bps=0))
    assert result.iloc[0]["gross_return"] == 0.0
    assert result["trading_cost"].sum() > 0


def test_missing_return_is_penalized_only_when_position_is_held():
    idx = pd.date_range("2025-01-01", periods=4, freq="D", tz="UTC")
    r = pd.DataFrame({"DEADUSDT": [0.0, 0.0, np.nan, np.nan]}, index=idx)
    w = pd.DataFrame({"DEADUSDT": [1.0, 1.0, 0.0, 0.0]}, index=idx)
    result = run_backtest(r, w, CostModel(0, 0, 0), missing_held_asset_return=-0.25)
    assert result.iloc[2]["missing_held_positions"] == 1.0
    assert abs(result.iloc[2]["gross_return"] + 0.25) < 1e-12
    assert result.iloc[3]["missing_held_positions"] == 0.0


def test_certification_is_fail_closed():
    metrics = performance_metrics(pd.Series([0.001] * 1000))
    decision = certification_decision(metrics, dsr_probability=0.50, pbo=0.10, stress_metrics=[metrics])
    assert decision["decision"] == "NO_GO"
    assert "DEFLATED_SHARPE_GATE_FAILED" in decision["reasons"]


def test_expected_max_sharpe_uses_cross_trial_dispersion():
    flat = expected_max_sharpe([1.0, 1.0, 1.0, 1.0])
    dispersed = expected_max_sharpe([0.0, 0.5, 1.0, 2.0])
    assert flat == 0.0
    assert dispersed > 0.0


def test_dsr_falls_when_benchmark_rises():
    low = deflated_sharpe_probability(1.0, 365, benchmark_sharpe=0.0)
    high = deflated_sharpe_probability(1.0, 365, benchmark_sharpe=0.8)
    assert 0.0 <= high <= low <= 1.0


def test_dsr_preserves_annualization_equivalence():
    annual = deflated_sharpe_probability(1.2, 730, benchmark_sharpe=0.4, periods_per_year=365)
    observation_scale = deflated_sharpe_probability(
        1.2 / np.sqrt(365), 730, benchmark_sharpe=0.4 / np.sqrt(365), periods_per_year=1
    )
    assert abs(annual - observation_scale) < 1e-12


def test_compounded_growth_can_fail_despite_positive_arithmetic_mean():
    r = pd.Series([1.0, -0.60] * 100)
    m = performance_metrics(r)
    assert m["expectancy"] > 0
    assert m["mean_log_return"] < 0
    decision = certification_decision(m, dsr_probability=1.0, pbo=0.0, stress_metrics=[m], min_trades=1, min_dsr=0.0)
    assert "NON_POSITIVE_COMPOUNDED_GROWTH" in decision["reasons"]


def test_performance_metrics_detects_losses():
    m = performance_metrics(pd.Series([-0.01] * 30))
    assert m["expectancy"] < 0
