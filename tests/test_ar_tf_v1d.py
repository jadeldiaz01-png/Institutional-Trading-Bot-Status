import numpy as np
import pandas as pd

from ar_tf.tournament import TournamentGate, TrialSpec, evaluate_trial, select_candidate


def _idx(n=320):
    return pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")


def test_tournament_never_opens_holdout():
    idx = _idx()
    specs = [
        TrialSpec("a", "structural", {"x": 1}),
        TrialSpec("b", "ridge", {"x": 2}),
    ]

    def run(spec, cost_multiplier):
        base = 0.0015 if spec.trial_id == "a" else 0.0010
        x = np.sin(np.arange(len(idx)) / 7.0) * 0.002 + base - (cost_multiplier - 1.0) * 0.0001
        return pd.Series(x, index=idx)

    results = [evaluate_trial(s, run) for s in specs]
    report = select_candidate(
        results,
        TournamentGate(min_dsr_probability=0.0, max_pbo=1.0),
        pbo_slices=8,
    )
    assert report["holdout_evaluated"] is False
    assert report["decision"] in {"FROZEN_HOLDOUT_CANDIDATE", "NO_GO"}


def test_missing_competition_fails_closed():
    idx = _idx()
    spec = TrialSpec("only", "structural", {})

    def run(_spec, _cost_multiplier):
        return pd.Series(np.full(len(idx), 0.001), index=idx)

    one = evaluate_trial(spec, run)
    report = select_candidate([one])
    assert report["decision"] == "NO_GO"
    assert "INSUFFICIENT_REGISTERED_TRIALS" in report["reasons"]


def test_cost_stress_can_disqualify_trial():
    idx = _idx()
    specs = [TrialSpec("a", "structural", {}), TrialSpec("b", "ridge", {})]

    def run(spec, cost_multiplier):
        edge = 0.001 if spec.trial_id == "a" else 0.0008
        stressed = edge - (cost_multiplier - 1.0) * 0.0012
        noise = np.sin(np.arange(len(idx)) / 5.0) * 0.0005
        return pd.Series(stressed + noise, index=idx)

    results = [evaluate_trial(s, run) for s in specs]
    report = select_candidate(
        results,
        TournamentGate(min_dsr_probability=0.0, max_pbo=1.0),
        pbo_slices=8,
    )
    assert report["decision"] == "NO_GO"
    assert all("COST_STRESS_GATE_FAILED" in t["reasons"] for t in report["trials"])


def test_stress_timestamp_mismatch_is_rejected():
    idx = _idx(30)
    spec = TrialSpec("a", "structural", {})

    def run(_spec, cost_multiplier):
        use = idx if cost_multiplier == 1.0 else idx[:-1]
        return pd.Series(np.full(len(use), 0.001), index=use)

    try:
        evaluate_trial(spec, run)
    except ValueError as exc:
        assert "same OOS timestamps" in str(exc)
    else:
        raise AssertionError("timestamp mismatch must fail closed")
