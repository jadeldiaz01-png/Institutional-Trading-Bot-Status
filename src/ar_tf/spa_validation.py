from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from arch.bootstrap import SPA


@dataclass(frozen=True)
class SPAConfig:
    reps: int = 2000
    block_size: int = 20
    seed: int = 29
    alpha: float = 0.05
    bootstrap: str = "stationary"
    studentize: bool = True


def _align(strategy_returns: pd.DataFrame, benchmark_returns: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    x = strategy_returns.astype(float).replace([np.inf, -np.inf], np.nan)
    b = benchmark_returns.astype(float).replace([np.inf, -np.inf], np.nan)
    joined = x.join(b.rename("__benchmark__"), how="inner").dropna()
    if joined.empty:
        raise ValueError("no common finite timestamps")
    if joined.index.has_duplicates:
        raise ValueError("duplicate timestamps")
    if joined.shape[1] < 3:
        raise ValueError("SPA requires at least two alternative strategies")
    return joined.drop(columns="__benchmark__"), joined["__benchmark__"]


def hansen_spa(
    strategy_returns: pd.DataFrame,
    benchmark_returns: pd.Series,
    cfg: SPAConfig = SPAConfig(),
) -> dict:
    """Hansen (2005) Superior Predictive Ability test for preregistered returns.

    ``arch.bootstrap.SPA`` is used rather than a local approximation so the
    studentized statistic, stationary bootstrap, and Hansen sample-dependent
    re-centering are implemented by a maintained reference library.

    SPA is formulated in losses (smaller is better). Strategy and benchmark
    returns are therefore mapped to loss = -return. The governance gate uses
    the *consistent* p-value, which is the standard Hansen re-centering choice.
    """
    if cfg.reps < 250:
        raise ValueError("SPA requires at least 250 bootstrap replications")
    if not 0.0 < cfg.alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    x, b = _align(strategy_returns, benchmark_returns)
    if len(x) < max(40, cfg.block_size * 2):
        return {
            "passed": False,
            "p_value_lower": 1.0,
            "p_value_consistent": 1.0,
            "p_value_upper": 1.0,
            "best_strategy": "",
            "best_mean_excess": float("nan"),
            "superior_models": [],
            "trial_count": int(x.shape[1]),
            "n": int(len(x)),
            "reason": "INSUFFICIENT_OBSERVATIONS",
        }

    excess = x.sub(b, axis=0)
    means = excess.mean(axis=0)
    best = str(means.idxmax())
    best_mean = float(means.max())

    spa = SPA(
        benchmark=(-b).to_numpy(dtype=float),
        models=(-x).to_numpy(dtype=float),
        block_size=int(cfg.block_size),
        reps=int(cfg.reps),
        bootstrap=cfg.bootstrap,
        studentize=bool(cfg.studentize),
        nested=False,
        seed=int(cfg.seed),
    )
    spa.compute()
    p = spa.pvalues
    lower = float(p.loc["lower"])
    consistent = float(p.loc["consistent"])
    upper = float(p.loc["upper"])
    if not (0.0 <= lower <= consistent <= upper <= 1.0):
        raise RuntimeError("invalid SPA p-value ordering")

    superior_idx = spa.better_models(pvalue=float(cfg.alpha), pvalue_type="consistent")
    columns = list(x.columns)
    superior_models = [columns[int(i)] if isinstance(i, (int, np.integer)) else str(i) for i in superior_idx]

    passed = bool(best_mean > 0.0 and consistent < cfg.alpha and len(superior_models) > 0)
    return {
        "passed": passed,
        "p_value_lower": lower,
        "p_value_consistent": consistent,
        "p_value_upper": upper,
        "best_strategy": best,
        "best_mean_excess": best_mean,
        "superior_models": superior_models,
        "trial_count": int(x.shape[1]),
        "n": int(len(x)),
        "bootstrap": cfg.bootstrap,
        "studentized": bool(cfg.studentize),
        "block_size": int(cfg.block_size),
        "reps": int(cfg.reps),
        "reason": "PASS" if passed else "SPA_NOT_SIGNIFICANT",
    }
