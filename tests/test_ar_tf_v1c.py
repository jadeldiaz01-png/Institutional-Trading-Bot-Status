import numpy as np
import pandas as pd

from ar_tf.alpha_lab import AlphaLabConfig, cost_aware_trade_gate, dispersion_state, turnover_limiter
from ar_tf.model_research import RidgeForecaster, forward_return, purged_train_test


def test_cost_gate_rejects_edge_below_cost_and_uncertainty():
    idx = pd.date_range("2026-01-01", periods=2, tz="UTC")
    f = pd.DataFrame({"BTCUSDT": [0.001, 0.010]}, index=idx)
    u = pd.DataFrame({"BTCUSDT": [0.001, 0.001]}, index=idx)
    gate = cost_aware_trade_gate(f, u, 10.0, AlphaLabConfig(min_expected_edge_bps=10.0))
    assert gate.iloc[0, 0] == 0.0
    assert gate.iloc[1, 0] == 1.0


def test_dispersion_scale_does_not_use_future_rows():
    idx = pd.date_range("2024-01-01", periods=400, freq="D", tz="UTC")
    r = pd.DataFrame({"A": np.sin(np.arange(400) / 20) / 100, "B": np.cos(np.arange(400) / 20) / 100}, index=idx)
    base = dispersion_state(r)
    altered = r.copy()
    altered.iloc[-1] = [0.9, -0.9]
    changed = dispersion_state(altered)
    pd.testing.assert_series_equal(base.iloc[:-1]["momentum_scale"], changed.iloc[:-1]["momentum_scale"])


def test_turnover_limiter_enforces_budget():
    prev = pd.Series({"A": 0.0, "B": 0.0})
    target = pd.Series({"A": 0.7, "B": 0.3})
    limited = turnover_limiter(prev, target, max_turnover=0.2)
    assert limited.sub(prev).abs().sum() <= 0.2 + 1e-12


def test_forward_label_is_future_only():
    s = pd.Series([100.0, 110.0, 121.0])
    y = forward_return(s, horizon=1)
    assert abs(y.iloc[0] - 0.10) < 1e-12
    assert pd.isna(y.iloc[-1])


def test_purged_split_has_no_overlap():
    idx = pd.date_range("2025-01-01", periods=300, freq="D", tz="UTC")
    tr, te = purged_train_test(idx, pd.Timestamp("2025-07-01", tz="UTC"), pd.Timestamp("2025-07-10", tz="UTC"), pd.Timestamp("2025-08-01", tz="UTC"), embargo_days=7)
    assert tr.max() < te.min()


def test_ridge_forecaster_is_deterministic():
    idx = pd.date_range("2025-01-01", periods=200, freq="D", tz="UTC")
    x = pd.DataFrame({"x1": np.linspace(-1, 1, 200), "x2": np.sin(np.arange(200) / 10)}, index=idx)
    y = 0.01 * x["x1"] - 0.005 * x["x2"]
    a = RidgeForecaster(alpha=1.0).fit(x, y).predict(x.tail(10))
    b = RidgeForecaster(alpha=1.0).fit(x, y).predict(x.tail(10))
    pd.testing.assert_series_equal(a, b)
