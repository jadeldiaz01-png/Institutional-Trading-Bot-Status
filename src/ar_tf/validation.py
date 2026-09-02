from __future__ import annotations

import itertools
import math
import numpy as np
import pandas as pd
from scipy.stats import norm


def performance_metrics(returns: pd.Series, periods_per_year: int = 365) -> dict[str, float]:
    r = returns.dropna().astype(float)
    if r.empty:
        return {
            "n": 0.0, "total_return": 0.0, "cagr": float("nan"),
            "mean_log_return": float("nan"), "geometric_mean_return": float("nan"),
            "sharpe": float("nan"), "sortino": float("nan"), "calmar": float("nan"),
            "annual_volatility": float("nan"), "max_drawdown": float("nan"),
            "profit_factor": float("nan"), "expectancy": float("nan"),
            "hit_rate": float("nan"), "var_95": float("nan"), "cvar_95": float("nan"),
            "skew": float("nan"), "kurtosis": float("nan"),
        }
    if (r <= -1.0).any():
        mean_log = float("-inf")
        geometric = -1.0
        cagr = -1.0
        equity = (1 + r).cumprod()
    else:
        log_r = np.log1p(r)
        mean_log = float(log_r.mean())
        geometric = float(np.expm1(mean_log))
        cagr = float(np.expm1(mean_log * periods_per_year))
        equity = np.exp(log_r.cumsum())
    dd = equity / equity.cummax() - 1
    std = r.std(ddof=1)
    annual_vol = float(std * np.sqrt(periods_per_year)) if std > 0 else 0.0
    sharpe = np.sqrt(periods_per_year) * r.mean() / std if std > 0 else float("nan")
    downside = r[r < 0]
    downside_std = downside.std(ddof=1) if len(downside) > 1 else float("nan")
    sortino = np.sqrt(periods_per_year) * r.mean() / downside_std if np.isfinite(downside_std) and downside_std > 0 else float("nan")
    max_dd = float(dd.min())
    calmar = cagr / abs(max_dd) if max_dd < 0 and np.isfinite(cagr) else float("nan")
    wins = r[r > 0].sum()
    losses = -r[r < 0].sum()
    pf = wins / losses if losses > 0 else float("inf")
    var95 = float(r.quantile(0.05))
    tail = r[r <= var95]
    cvar95 = float(tail.mean()) if not tail.empty else var95
    return {
        "n": float(len(r)),
        "total_return": float(equity.iloc[-1] - 1),
        "cagr": float(cagr),
        "mean_log_return": mean_log,
        "geometric_mean_return": geometric,
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "calmar": float(calmar),
        "annual_volatility": annual_vol,
        "max_drawdown": max_dd,
        "profit_factor": float(pf),
        "expectancy": float(r.mean()),
        "hit_rate": float((r > 0).mean()),
        "var_95": var95,
        "cvar_95": cvar95,
        "skew": float(r.skew()) if len(r) > 2 else float("nan"),
        "kurtosis": float(r.kurtosis() + 3.0) if len(r) > 3 else float("nan"),
    }


def _moving_block_sample(r: np.ndarray, block: int, rng: np.random.Generator) -> np.ndarray:
    draw: list[float] = []
    block = max(1, min(int(block), len(r)))
    while len(draw) < len(r):
        i = int(rng.integers(0, max(1, len(r) - block + 1)))
        draw.extend(r[i:i + block].tolist())
    return np.asarray(draw[:len(r)], dtype=float)


def bootstrap_sharpe(returns: pd.Series, samples: int = 2000, block: int = 20, seed: int = 7) -> np.ndarray:
    r = returns.dropna().to_numpy(dtype=float)
    if len(r) < 2:
        return np.array([])
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(samples):
        x = _moving_block_sample(r, block, rng)
        s = x.std(ddof=1)
        out.append(np.sqrt(365) * x.mean() / s if s > 0 else np.nan)
    return np.asarray(out)


def monte_carlo_drawdowns(returns: pd.Series, paths: int = 2000, seed: int = 11, block: int = 20) -> np.ndarray:
    """Moving-block bootstrap drawdowns; preserves local serial dependence."""
    r = returns.dropna().to_numpy(dtype=float)
    if len(r) == 0:
        return np.array([])
    rng = np.random.default_rng(seed)
    result = []
    for _ in range(paths):
        x = _moving_block_sample(r, block, rng)
        eq = np.cumprod(1 + x)
        peak = np.maximum.accumulate(eq)
        result.append(np.min(eq / peak - 1))
    return np.asarray(result)


def expected_max_sharpe(trial_sharpes: list[float] | np.ndarray) -> float:
    """Bailey-Lopez de Prado expected maximum Sharpe benchmark.

    Uses the cross-trial dispersion of the *registered trial Sharpe ratios* and
    their total count N. Inputs and output are on the same annualized scale.
    """
    x = np.asarray(trial_sharpes, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n <= 1:
        return 0.0
    sigma = float(np.std(x, ddof=1))
    if sigma <= 0 or not np.isfinite(sigma):
        return 0.0
    gamma = 0.5772156649015329
    z1 = norm.ppf(1.0 - 1.0 / n)
    z2 = norm.ppf(1.0 - 1.0 / (n * math.e))
    return float(sigma * ((1.0 - gamma) * z1 + gamma * z2))


def deflated_sharpe_probability(
    observed_sharpe: float,
    n_obs: int,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    benchmark_sharpe: float = 0.0,
    periods_per_year: int = 365,
) -> float:
    """Scale-consistent probabilistic/deflated Sharpe probability.

    Both observed and benchmark Sharpe are supplied on the annualized scale and
    de-annualized internally. In a tournament, ``benchmark_sharpe`` must be the
    expected maximum Sharpe computed from all preregistered trial Sharpes.
    """
    if n_obs < 3 or periods_per_year <= 0 or not np.isfinite(observed_sharpe) or not np.isfinite(benchmark_sharpe):
        return 0.0
    scale = math.sqrt(float(periods_per_year))
    sr = float(observed_sharpe) / scale
    sr0 = float(benchmark_sharpe) / scale
    denom_sq = (1.0 - skew * sr + ((kurtosis - 1.0) / 4.0) * sr**2) / max(1, n_obs - 1)
    if not np.isfinite(denom_sq) or denom_sq <= 0:
        return 0.0
    z = (sr - sr0) / math.sqrt(denom_sq)
    return float(norm.cdf(z))


def probability_of_backtest_overfitting(strategy_returns: pd.DataFrame, slices: int = 8) -> dict[str, float]:
    """CSCV-style PBO estimator over an exactly synchronous trial matrix."""
    if strategy_returns.isna().any(axis=None):
        return {"pbo": float("nan"), "combinations": 0.0, "median_logit": float("nan")}
    x = strategy_returns
    if x.shape[1] < 2 or len(x) < slices or slices < 4 or slices % 2:
        return {"pbo": float("nan"), "combinations": 0.0, "median_logit": float("nan")}
    blocks = np.array_split(np.arange(len(x)), slices)
    logits: list[float] = []
    all_blocks = set(range(slices))
    half = slices // 2
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


def certification_decision(
    metrics: dict,
    dsr_probability: float,
    pbo: float,
    stress_metrics: list[dict],
    *,
    min_trades: int = 100,
    max_pbo: float = 0.20,
    min_dsr: float = 0.95,
) -> dict:
    reasons = []
    if metrics.get("n", 0) < min_trades:
        reasons.append("INSUFFICIENT_OBSERVATIONS")
    if metrics.get("expectancy", -1) <= 0:
        reasons.append("NON_POSITIVE_NET_EXPECTANCY")
    if metrics.get("total_return", -1) <= 0 or metrics.get("mean_log_return", -1) <= 0:
        reasons.append("NON_POSITIVE_COMPOUNDED_GROWTH")
    if metrics.get("sharpe", -1) <= 0:
        reasons.append("NON_POSITIVE_OOS_SHARPE")
    if dsr_probability < min_dsr:
        reasons.append("DEFLATED_SHARPE_GATE_FAILED")
    if not np.isfinite(pbo) or pbo > max_pbo:
        reasons.append("PBO_GATE_FAILED")
    if not stress_metrics or any(
        m.get("expectancy", -1) <= 0
        or m.get("total_return", -1) <= 0
        or m.get("mean_log_return", -1) <= 0
        for m in stress_metrics
    ):
        reasons.append("COST_STRESS_FAILED")
    return {"decision": "PAPER_CANDIDATE" if not reasons else "NO_GO", "reasons": reasons}
