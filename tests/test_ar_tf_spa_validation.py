import numpy as np
import pandas as pd

from ar_tf.spa_validation import SPAConfig, hansen_spa


def _index(n=360):
    return pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")


def test_hansen_spa_detects_clear_superiority():
    idx = _index()
    rng = np.random.default_rng(7)
    benchmark = pd.Series(rng.normal(0.0, 0.001, len(idx)), index=idx)
    models = pd.DataFrame(
        {
            "strong": benchmark.to_numpy() + 0.0010 + rng.normal(0.0, 0.0002, len(idx)),
            "weak": benchmark.to_numpy() + 0.0002 + rng.normal(0.0, 0.0004, len(idx)),
            "bad": benchmark.to_numpy() - 0.0003 + rng.normal(0.0, 0.0004, len(idx)),
        },
        index=idx,
    )
    result = hansen_spa(models, benchmark, SPAConfig(reps=500, block_size=12, seed=11))
    assert result["p_value_lower"] <= result["p_value_consistent"] <= result["p_value_upper"]
    assert result["best_strategy"] == "strong"
    assert result["best_mean_excess"] > 0
    assert result["passed"] is True
    assert "strong" in result["superior_models"]


def test_hansen_spa_rejects_no_edge_family():
    idx = _index()
    rng = np.random.default_rng(17)
    benchmark = pd.Series(rng.normal(0.0001, 0.001, len(idx)), index=idx)
    models = pd.DataFrame(
        {
            "a": benchmark.to_numpy() - 0.0002 + rng.normal(0.0, 0.0003, len(idx)),
            "b": benchmark.to_numpy() - 0.0001 + rng.normal(0.0, 0.0003, len(idx)),
        },
        index=idx,
    )
    result = hansen_spa(models, benchmark, SPAConfig(reps=500, block_size=12, seed=19))
    assert result["passed"] is False
    assert result["best_mean_excess"] <= 0


def test_hansen_spa_fails_closed_on_insufficient_history():
    idx = _index(30)
    benchmark = pd.Series(np.zeros(len(idx)), index=idx)
    models = pd.DataFrame({"a": np.ones(len(idx)) * 0.001, "b": np.ones(len(idx)) * 0.0005}, index=idx)
    result = hansen_spa(models, benchmark, SPAConfig(reps=250, block_size=20, seed=23))
    assert result["passed"] is False
    assert result["reason"] == "INSUFFICIENT_OBSERVATIONS"
