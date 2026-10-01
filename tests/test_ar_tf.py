import numpy as np
import pandas as pd

from ar_tf.backtest import CostModel, run_backtest
from ar_tf.core import ResearchConfig, build_features, build_signal, portfolio_weights
from ar_tf.validation import certification_decision, performance_metrics


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


def test_certification_is_fail_closed():
    metrics = {"n": 1000, "expectancy": 0.001, "sharpe": 1.0}
    decision = certification_decision(metrics, dsr_probability=0.50, pbo=0.10, stress_metrics=[metrics])
    assert decision["decision"] == "NO_GO"
    assert "DEFLATED_SHARPE_GATE_FAILED" in decision["reasons"]


def test_performance_metrics_detects_losses():
    m = performance_metrics(pd.Series([-0.01] * 30))
    assert m["expectancy"] < 0
