from __future__ import annotations

import itertools
import math
import numpy as np
import pandas as pd
from scipy.stats import norm


def performance_metrics(returns: pd.Series, periods_per_year: int = 365) -> dict[str, float]:
    r = returns.dropna().astype(float)
    if r.empty:
        return {"n": 0.0, "total_return": 0.0, "sharpe": float("nan"), "max_drawdown": float("nan"), "profit_factor": float("nan"), "expectancy": float("nan")}
    equity = (1 + r).cumprod()
    dd = equity / equity.cummax() - 1
    std = r.std(ddof=1)
    sharpe = np.sqrt(periods_per_year) * r.mean() / std if std > 0 else float("nan")
    wins = r[r > 0].sum()
    losses = -r[r < 0].sum()
    pf = wins / losses if losses > 0 else float("inf")
    return {
        "n": float(len(r)),
        "total_return": float(equity.iloc[-1] - 1),
        "sharpe": float(sharpe),
        "max_drawdown": float(dd.min()),
        "profit_factor": float(pf),
        "expectancy": float(r.mean()),
    }


def bootstrap_sharpe(returns: pd.Series, samples: int = 2000, block: int = 20, seed: int = 7) -> np.ndarray:
    r = returns.dropna().to_numpy(dtype=float)
    if len(r) < 2:
        return np.array([])
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(samples):
        draw = []
        while len(draw) < len(r):
            i = rng.integers(0, max(1, len(r) - block + 1))
            draw.extend(r[i:i + block])
        x = np.asarray(draw[:len(r)])
        s = x.std(ddof=1)
        out.append(np.sqrt(365) * x.mean() / s if s > 0 else np.nan)
    return np.asarray(out)


def monte_carlo_drawdowns(returns: pd.Series, paths: int = 2000, seed: int = 11) -> np.ndarray:
    r = returns.dropna().to_numpy(dtype=float)
    if len(r) == 0:
        return np.array([])
    rng = np.random.default_rng(seed)
    result = []
    for _ in range(paths):
        x = rng.permutation(r)
        eq = np.cumprod(1 + x)
        peak = np.maximum.accumulate(eq)
        result.append(np.min(eq / peak - 1))
    return np.asarray(result)


def deflated_sharpe_probability(
    observed_sharpe: float,
    n_obs: int,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    trials: int = 1,
    periods_per_year: int = 365,
) -> float:
    """Conservative DSR-style probability with scale-consistent Sharpe inputs.

    ``performance_metrics`` reports an annualized Sharpe. The probabilistic/
    deflated Sharpe expression is evaluated on the per-observation Sharpe, so
    the statistic is de-annualized here before applying skew/kurtosis and trial
    multiplicity penalties. The expected maximum under multiple trials uses the
    Bailey-Lopez de Prado extreme-value approximation with Euler's constant.

    This remains a research approximation, not a substitute for reporting the
    full trial distribution, CPCV/PBO and bootstrap evidence.
    """
    if n_obs < 3 or periods_per_year <= 0 or not np.isfinite(observed_sharpe):
        return 0.0
    trials = max(1, int(trials))
    sr = float(observed_sharpe) / math.sqrt(float(periods_per_year))
    if trials > 1:
        sr_std_null = 1.0 / math.sqrt(max(1, n_obs - 1))
        gamma = 0.5772156649015329
        z1 = norm.ppf(1.0 - 1.0 / trials)
        z2 = norm.ppf(1.0 - 1.0 / (trials * math.e))
        expected_max = sr_std_null * ((1.0 - gamma) * z1 + gamma * z2)
    else:
        expected_max = 0.0
    denom_sq = (1.0 - skew * sr + ((kurtosis - 1.0) / 4.0) * sr**2) / max(1, n_obs - 1)
    if not np.isfinite(denom_sq) or denom_sq <= 0:
        return 0.0
    z = (sr - expected_max) / math.sqrt(denom_sq)
    return float(norm.cdf(z))


def probability_of_backtest_overfitting(strategy_returns: pd.DataFrame, slices: int = 8) -> dict[str, float]:
    """CSCV-style PBO estimator.

    Columns are competing parameterizations/strategies and rows are synchronous
    OOS-candidate returns. The sample is split into an even number of contiguous
    slices. For each half-combination, choose the best in-sample Sharpe and rank
    that same candidate out-of-sample. PBO is P(logit(relative OOS rank) <= 0).
    """
    x = strategy_returns.dropna(how="any")
    if x.shape[1] < 2 or len(x) < slices or slices < 4 or slices % 2:
        return {"pbo": float("nan"), "combinations": 0.0, "median_logit": float("nan")}
    blocks = np.array_split(np.arange(len(x)), slices)
    logits: list[float] = []
    all_blocks = set(range(slices))
    half = slices // 2
    # Symmetric complements are duplicates; keep combinations containing block 0.
    combos = [c for c in itertools.combinations(range(slices), half) if 0 in c]
    for combo in combos:
        train_idx = np.concatenate([blocks[i] for i in combo])
        test_blocks = sorted(all_blocks - set(combo))
        test_idx = np.concatenate([blocks[i] for i in test_blocks])
        train = x.iloc[train_idx]
        test = x.iloc[test_idx]
        train_std = train.std(ddof=1).replace(0, np.nan)
        test_std = test.std(ddof=1).replace(0, np.nan)
        train_sr = train.mean() / train_std
        test_sr = test.mean() / test_std
        if train_sr.dropna().empty or test_sr.dropna().empty:
            continue
        winner = train_sr.idxmax()
        ranked = test_sr.rank(method="average", ascending=True)
        rank = float(ranked.loc[winner])
        n = float(ranked.notna().sum())
        omega = rank / (n + 1.0)
        omega = float(np.clip(omega, 1e-12, 1 - 1e-12))
        logits.append(math.log(omega / (1.0 - omega)))
    if not logits:
        return {"pbo": float("nan"), "combinations": 0.0, "median_logit": float("nan")}
    arr = np.asarray(logits)
    return {
        "pbo": float(np.mean(arr <= 0.0)),
        "combinations": float(len(arr)),
        "median_logit": float(np.median(arr)),
    }


def certification_decision(metrics: dict, dsr_probability: float, pbo: float, stress_metrics: list[dict], *, min_trades: int = 100, max_pbo: float = 0.20, min_dsr: float = 0.95) -> dict:
    reasons = []
    if metrics.get("n", 0) < min_trades:
        reasons.append("INSUFFICIENT_OBSERVATIONS")
    if metrics.get("expectancy", -1) <= 0:
        reasons.append("NON_POSITIVE_NET_EXPECTANCY")
    if metrics.get("sharpe", -1) <= 0:
        reasons.append("NON_POSITIVE_OOS_SHARPE")
    if dsr_probability < min_dsr:
        reasons.append("DEFLATED_SHARPE_GATE_FAILED")
    if not np.isfinite(pbo) or pbo > max_pbo:
        reasons.append("PBO_GATE_FAILED")
    if not stress_metrics or any(m.get("expectancy", -1) <= 0 for m in stress_metrics):
        reasons.append("COST_STRESS_FAILED")
    return {"decision": "PAPER_CANDIDATE" if not reasons else "NO_GO", "reasons": reasons}
