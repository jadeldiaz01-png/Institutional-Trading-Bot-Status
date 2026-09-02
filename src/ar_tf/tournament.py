from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
from typing import Callable

import numpy as np
import pandas as pd

from .validation import (
    deflated_sharpe_probability,
    expected_max_sharpe,
    performance_metrics,
    probability_of_backtest_overfitting,
)


@dataclass(frozen=True)
class TournamentGate:
    min_oos_sharpe: float = 0.0
    min_oos_expectancy: float = 0.0
    min_dsr_probability: float = 0.95
    max_pbo: float = 0.20
    min_cost_stress_expectancy: float = 0.0
    min_trials: int = 2


@dataclass(frozen=True)
class TrialSpec:
    trial_id: str
    family: str
    params: dict
    seed: int = 7

    @property
    def digest(self) -> str:
        payload = json.dumps(
            {"trial_id": self.trial_id, "family": self.family, "params": self.params, "seed": self.seed},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


@dataclass
class TrialResult:
    spec: TrialSpec
    returns: pd.Series
    metrics: dict[str, float]
    stress_metrics: list[dict[str, float]]


def _clean_returns(x: pd.Series) -> pd.Series:
    y = x.astype(float).replace([np.inf, -np.inf], np.nan).dropna().sort_index()
    if y.index.has_duplicates:
        raise ValueError("duplicate timestamps in trial returns")
    return y


def evaluate_trial(
    spec: TrialSpec,
    run_fn: Callable[[TrialSpec, float], pd.Series],
    cost_multipliers: tuple[float, ...] = (1.0, 2.0, 3.0),
) -> TrialResult:
    base = _clean_returns(run_fn(spec, 1.0))
    if base.empty:
        raise ValueError(f"trial {spec.trial_id} produced no OOS returns")
    stress = []
    for multiplier in cost_multipliers:
        stressed = _clean_returns(run_fn(spec, float(multiplier)))
        if not stressed.index.equals(base.index):
            raise ValueError("stress scenarios must use the exact same OOS timestamps")
        stress.append(performance_metrics(stressed))
    return TrialResult(spec=spec, returns=base, metrics=performance_metrics(base), stress_metrics=stress)


def aligned_trial_matrix(results: list[TrialResult]) -> pd.DataFrame:
    if len(results) < 2:
        raise ValueError("PBO requires at least two competing trials")
    ids = [r.spec.trial_id for r in results]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate trial_id values")
    reference = results[0].returns.index
    for result in results[1:]:
        if not result.returns.index.equals(reference):
            raise ValueError("all trials must use the exact same synchronous OOS timestamps")
    matrix = pd.DataFrame({r.spec.trial_id: r.returns.to_numpy(dtype=float) for r in results}, index=reference)
    if matrix.empty or matrix.isna().any(axis=None):
        raise ValueError("invalid synchronous OOS trial matrix")
    return matrix


def select_candidate(
    results: list[TrialResult],
    gate: TournamentGate = TournamentGate(),
    pbo_slices: int = 8,
) -> dict:
    """Select one research candidate without opening the frozen holdout."""
    if len(results) < gate.min_trials:
        return {"decision": "NO_GO", "reasons": ["INSUFFICIENT_REGISTERED_TRIALS"], "holdout_evaluated": False}

    matrix = aligned_trial_matrix(results)
    pbo_stats = probability_of_backtest_overfitting(matrix, slices=pbo_slices)
    pbo = float(pbo_stats["pbo"])
    if not np.isfinite(pbo):
        return {"decision": "NO_GO", "reasons": ["PBO_UNAVAILABLE"], "holdout_evaluated": False, "pbo": None}

    all_trial_sharpes = [float(r.metrics.get("sharpe", np.nan)) for r in results]
    dsr_benchmark = expected_max_sharpe(all_trial_sharpes)
    scored = []
    for result in results:
        r = result.returns
        m = result.metrics
        skew = float(r.skew()) if len(r) > 2 else 0.0
        kurtosis = float(r.kurtosis() + 3.0) if len(r) > 3 else 3.0
        dsr = deflated_sharpe_probability(
            float(m.get("sharpe", np.nan)), len(r), skew, kurtosis,
            benchmark_sharpe=dsr_benchmark,
        )
        stress_ok = bool(result.stress_metrics) and all(
            np.isfinite(float(x.get("expectancy", np.nan)))
            and float(x.get("expectancy", -np.inf)) > gate.min_cost_stress_expectancy
            and float(x.get("total_return", -np.inf)) > 0.0
            and float(x.get("mean_log_return", -np.inf)) > 0.0
            for x in result.stress_metrics
        )
        reasons = []
        if not np.isfinite(float(m.get("sharpe", np.nan))) or float(m.get("sharpe", -np.inf)) <= gate.min_oos_sharpe:
            reasons.append("OOS_SHARPE_GATE_FAILED")
        if not np.isfinite(float(m.get("expectancy", np.nan))) or float(m.get("expectancy", -np.inf)) <= gate.min_oos_expectancy:
            reasons.append("OOS_EXPECTANCY_GATE_FAILED")
        if float(m.get("total_return", -np.inf)) <= 0.0 or float(m.get("mean_log_return", -np.inf)) <= 0.0:
            reasons.append("COMPOUNDED_GROWTH_GATE_FAILED")
        if not np.isfinite(dsr) or dsr < gate.min_dsr_probability:
            reasons.append("DSR_GATE_FAILED")
        if pbo > gate.max_pbo:
            reasons.append("PBO_GATE_FAILED")
        if not stress_ok:
            reasons.append("COST_STRESS_GATE_FAILED")
        scored.append({
            "trial_id": result.spec.trial_id,
            "family": result.spec.family,
            "trial_digest": result.spec.digest,
            "metrics": m,
            "dsr_probability": float(dsr),
            "eligible": not reasons,
            "reasons": reasons,
        })

    eligible = [x for x in scored if x["eligible"]]
    common = {
        "holdout_evaluated": False,
        "pbo": pbo,
        "pbo_combinations": pbo_stats["combinations"],
        "dsr_benchmark_sharpe": dsr_benchmark,
        "registered_trial_count": len(results),
        "trials": scored,
    }
    if not eligible:
        return {"decision": "NO_GO", "reasons": ["NO_TRIAL_SURVIVED_ALL_GATES"], **common}

    eligible.sort(
        key=lambda x: (
            float(x["dsr_probability"]),
            float(x["metrics"]["sharpe"]),
            float(x["metrics"]["expectancy"]),
        ),
        reverse=True,
    )
    winner = eligible[0]
    return {
        "decision": "FROZEN_HOLDOUT_CANDIDATE",
        "reasons": [],
        **common,
        "winner": winner,
        "gate": asdict(gate),
        "required_next_gate": "SINGLE_UNTOUCHED_365D_HOLDOUT",
    }
