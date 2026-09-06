from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BootstrapConfig:
    samples: int = 2000
    block: int = 20
    seed: int = 17
    alpha: float = 0.05


def _aligned_frame(strategy_returns: pd.DataFrame, benchmark_returns: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    x = strategy_returns.astype(float).replace([np.inf, -np.inf], np.nan)
    b = benchmark_returns.astype(float).replace([np.inf, -np.inf], np.nan)
    joined = x.join(b.rename("__benchmark__"), how="inner").dropna()
    if joined.empty:
        raise ValueError("no common finite timestamps")
    if joined.index.has_duplicates:
        raise ValueError("duplicate timestamps")
    return joined.drop(columns="__benchmark__"), joined["__benchmark__"]


def _moving_block_indices(n: int, block: int, rng: np.random.Generator) -> np.ndarray:
    block = max(1, min(int(block), n))
    out: list[int] = []
    while len(out) < n:
        start = int(rng.integers(0, max(1, n - block + 1)))
        out.extend(range(start, min(start + block, n)))
    return np.asarray(out[:n], dtype=int)


def paired_block_bootstrap_superiority(
    candidate_returns: pd.Series,
    benchmark_returns: pd.Series,
    cfg: BootstrapConfig = BootstrapConfig(),
) -> dict[str, float | bool]:
    pair = pd.concat([candidate_returns.rename("candidate"), benchmark_returns.rename("benchmark")], axis=1).dropna()
    if len(pair) < max(30, cfg.block * 2):
        return {"passed": False, "n": float(len(pair)), "mean_excess": float("nan"), "ci_lower": float("nan"), "ci_upper": float("nan"), "p_nonpositive": 1.0}
    d = (pair["candidate"] - pair["benchmark"]).to_numpy(dtype=float)
    rng = np.random.default_rng(cfg.seed)
    boot = np.empty(cfg.samples, dtype=float)
    for i in range(cfg.samples):
        boot[i] = float(d[_moving_block_indices(len(d), cfg.block, rng)].mean())
    lo, hi = np.quantile(boot, [cfg.alpha / 2.0, 1.0 - cfg.alpha / 2.0])
    return {
        "passed": bool(lo > 0.0),
        "n": float(len(d)),
        "mean_excess": float(d.mean()),
        "ci_lower": float(lo),
        "ci_upper": float(hi),
        "p_nonpositive": float(np.mean(boot <= 0.0)),
    }


def white_reality_check(
    strategy_returns: pd.DataFrame,
    benchmark_returns: pd.Series,
    cfg: BootstrapConfig = BootstrapConfig(),
) -> dict[str, float | bool | str]:
    """White-style max-statistic reality check using moving-block bootstrap.

    The test is applied to the entire preregistered strategy family against one
    benchmark. Differentials are centered under the null before resampling so
    the p-value reflects data-snooping across all submitted alternatives.
    """
    x, b = _aligned_frame(strategy_returns, benchmark_returns)
    if x.shape[1] < 2 or len(x) < max(30, cfg.block * 2):
        return {"passed": False, "p_value": 1.0, "best_strategy": "", "best_mean_excess": float("nan"), "trial_count": float(x.shape[1]), "n": float(len(x))}
    d = x.sub(b, axis=0)
    means = d.mean(axis=0)
    best = str(means.idxmax())
    observed = math.sqrt(len(d)) * float(means.max())
    centered = d - means
    arr = centered.to_numpy(dtype=float)
    rng = np.random.default_rng(cfg.seed)
    stats = np.empty(cfg.samples, dtype=float)
    for i in range(cfg.samples):
        sample = arr[_moving_block_indices(len(arr), cfg.block, rng)]
        stats[i] = math.sqrt(len(arr)) * float(np.max(sample.mean(axis=0)))
    p = float((1.0 + np.sum(stats >= observed)) / (cfg.samples + 1.0))
    return {
        "passed": bool(float(means.max()) > 0.0 and p < cfg.alpha),
        "p_value": p,
        "best_strategy": best,
        "best_mean_excess": float(means.max()),
        "trial_count": float(x.shape[1]),
        "n": float(len(x)),
    }


def parameter_plateau_test(
    metric_by_parameter: pd.Series,
    *,
    relative_tolerance: float = 0.15,
    min_plateau_fraction: float = 0.60,
    neighborhood: int = 1,
) -> dict[str, float | bool]:
    """Reject a candidate whose optimum is an isolated parameter spike."""
    s = metric_by_parameter.astype(float).replace([np.inf, -np.inf], np.nan).dropna().sort_index()
    if len(s) < 3:
        return {"passed": False, "best": float("nan"), "plateau_fraction": 0.0, "neighbor_count": float(len(s))}
    best_pos = int(np.argmax(s.to_numpy()))
    best = float(s.iloc[best_pos])
    lo = max(0, best_pos - int(neighborhood))
    hi = min(len(s), best_pos + int(neighborhood) + 1)
    local = s.iloc[lo:hi]
    if best <= 0.0:
        return {"passed": False, "best": best, "plateau_fraction": 0.0, "neighbor_count": float(len(local))}
    threshold = best * (1.0 - relative_tolerance)
    fraction = float((local >= threshold).mean())
    return {"passed": bool(len(local) >= 2 and fraction >= min_plateau_fraction), "best": best, "plateau_fraction": fraction, "neighbor_count": float(len(local))}


def regime_stability_test(
    returns: pd.Series,
    regimes: pd.Series,
    *,
    min_observations_per_regime: int = 20,
    min_positive_regime_fraction: float = 0.67,
    catastrophic_mean_floor: float = -0.002,
) -> dict:
    frame = pd.concat([returns.rename("r"), regimes.rename("regime")], axis=1).dropna()
    details: dict[str, dict[str, float]] = {}
    eligible = []
    for name, group in frame.groupby("regime"):
        if len(group) < min_observations_per_regime:
            continue
        mean = float(group["r"].mean())
        details[str(name)] = {"n": float(len(group)), "mean": mean}
        eligible.append(mean)
    if not eligible:
        return {"passed": False, "positive_regime_fraction": 0.0, "worst_regime_mean": float("nan"), "details": details}
    positive_fraction = float(np.mean(np.asarray(eligible) > 0.0))
    worst = float(min(eligible))
    return {
        "passed": bool(positive_fraction >= min_positive_regime_fraction and worst > catastrophic_mean_floor),
        "positive_regime_fraction": positive_fraction,
        "worst_regime_mean": worst,
        "details": details,
    }


def model_incremental_value_gate(
    *,
    candidate_net_sharpe: float,
    baseline_net_sharpe: float,
    superiority: dict,
    base_cost_passed: bool,
    stressed_cost_passed: bool,
    multiplicity_adjusted: bool,
    no_holdout_tuning: bool,
) -> dict:
    """Admission gate for XGBoost/LSTM/Transformer/RL challengers.

    Forecast accuracy is deliberately absent: a complex model is admitted only
    for incremental economic value after costs and statistical controls.
    """
    reasons: list[str] = []
    if not np.isfinite(candidate_net_sharpe) or candidate_net_sharpe <= baseline_net_sharpe:
        reasons.append("NO_INCREMENTAL_NET_SHARPE")
    if not bool(superiority.get("passed", False)):
        reasons.append("PAIRED_SUPERIORITY_FAILED")
    if not base_cost_passed or not stressed_cost_passed:
        reasons.append("COST_STRESS_FAILED")
    if not multiplicity_adjusted:
        reasons.append("MULTIPLICITY_NOT_ADJUSTED")
    if not no_holdout_tuning:
        reasons.append("HOLDOUT_CONTAMINATION_RISK")
    return {"decision": "ADMIT_CHALLENGER" if not reasons else "REJECT_CHALLENGER", "reasons": reasons}
