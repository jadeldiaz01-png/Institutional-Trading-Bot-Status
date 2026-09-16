import numpy as np
import pandas as pd

from ar_tf.advanced_validation import (
    BootstrapConfig,
    model_incremental_value_gate,
    paired_block_bootstrap_superiority,
    parameter_plateau_test,
    regime_stability_test,
    white_reality_check,
)


def _idx(n=240):
    return pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")


def test_paired_bootstrap_detects_clear_superiority():
    idx = _idx()
    benchmark = pd.Series(np.zeros(len(idx)), index=idx)
    candidate = pd.Series(np.full(len(idx), 0.001), index=idx)
    out = paired_block_bootstrap_superiority(candidate, benchmark, BootstrapConfig(samples=300, block=10, seed=1))
    assert out["passed"] is True
    assert out["ci_lower"] > 0


def test_white_reality_check_counts_whole_family():
    idx = _idx()
    benchmark = pd.Series(np.zeros(len(idx)), index=idx)
    strategies = pd.DataFrame({
        "weak": np.zeros(len(idx)),
        "strong": np.full(len(idx), 0.001),
        "bad": np.full(len(idx), -0.001),
    }, index=idx)
    out = white_reality_check(strategies, benchmark, BootstrapConfig(samples=300, block=10, seed=2))
    assert out["trial_count"] == 3
    assert out["best_strategy"] == "strong"
    assert out["passed"] is True


def test_parameter_plateau_rejects_isolated_spike():
    s = pd.Series([0.1, 0.1, 1.0, 0.1, 0.1], index=[10, 20, 30, 40, 50])
    out = parameter_plateau_test(s, relative_tolerance=0.15, min_plateau_fraction=0.60, neighborhood=1)
    assert out["passed"] is False


def test_parameter_plateau_accepts_broad_region():
    s = pd.Series([0.6, 0.9, 1.0, 0.92, 0.6], index=[10, 20, 30, 40, 50])
    out = parameter_plateau_test(s, relative_tolerance=0.15, min_plateau_fraction=0.60, neighborhood=1)
    assert out["passed"] is True


def test_regime_stability_rejects_catastrophic_regime():
    idx = _idx(180)
    regimes = pd.Series(["bull"] * 60 + ["sideways"] * 60 + ["bear"] * 60, index=idx)
    returns = pd.Series([0.001] * 60 + [0.0005] * 60 + [-0.01] * 60, index=idx)
    out = regime_stability_test(returns, regimes, min_observations_per_regime=20)
    assert out["passed"] is False


def test_complex_model_cannot_enter_on_accuracy_alone():
    out = model_incremental_value_gate(
        candidate_net_sharpe=1.2,
        baseline_net_sharpe=1.0,
        superiority={"passed": False},
        base_cost_passed=True,
        stressed_cost_passed=True,
        multiplicity_adjusted=True,
        no_holdout_tuning=True,
    )
    assert out["decision"] == "REJECT_CHALLENGER"
    assert "PAIRED_SUPERIORITY_FAILED" in out["reasons"]
