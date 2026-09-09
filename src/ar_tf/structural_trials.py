from __future__ import annotations

import numpy as np
import pandas as pd

from .research_panel import ResearchPanel, inverse_vol_weights, rolling_liquidity_universe


def _equal_weight(mask_or_score: pd.DataFrame) -> pd.DataFrame:
    x = mask_or_score.astype(float).clip(lower=0.0)
    denom = x.sum(axis=1).replace(0.0, np.nan)
    return x.div(denom, axis=0).fillna(0.0)


def _apply_universe(signal: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    a, u = signal.align(universe, join="inner", axis=0)
    a, u = a.align(u, join="inner", axis=1)
    return a.where(u, 0.0).fillna(0.0)


def time_series_momentum(panel: ResearchPanel, params: dict) -> pd.DataFrame:
    lb = int(params["lookback_days"])
    rebalance = int(params["rebalance_days"])
    vol_targeting = bool(params["volatility_targeting"])
    universe = rolling_liquidity_universe(panel, max_assets=15)
    mom = panel.close.pct_change(lb, fill_method=None).shift(1)
    signal = _apply_universe((mom > 0).astype(float), universe)
    if rebalance > 1:
        sampled = signal.iloc[::rebalance]
        signal = sampled.reindex(signal.index).ffill().fillna(0.0)
    if vol_targeting:
        return inverse_vol_weights(signal, panel.returns)
    return _equal_weight(signal)


def donchian_breakout(panel: ResearchPanel, params: dict) -> pd.DataFrame:
    lb = int(params["lookback_days"])
    rebalance = int(params["rebalance_days"])
    universe = rolling_liquidity_universe(panel, max_assets=15)
    threshold = panel.high.shift(2).rolling(lb, min_periods=lb).max()
    signal = _apply_universe((panel.close.shift(1) > threshold).astype(float), universe)
    if rebalance > 1:
        signal = signal.iloc[::rebalance].reindex(signal.index).ffill().fillna(0.0)
    return inverse_vol_weights(signal, panel.returns)


def cross_sectional_momentum(panel: ResearchPanel, params: dict) -> pd.DataFrame:
    formation = int(params["formation_days"])
    top_fraction = float(params["top_fraction"])
    universe_size = int(params["universe_size"])
    universe = rolling_liquidity_universe(panel, max_assets=universe_size)
    mom = panel.close.pct_change(formation, fill_method=None).shift(1).where(universe)
    pct_rank = mom.rank(axis=1, pct=True, ascending=True)
    signal = ((pct_rank >= 1.0 - top_fraction) & universe).astype(float)
    return inverse_vol_weights(signal, panel.returns)


def lagged_dispersion_momentum(panel: ResearchPanel, params: dict) -> pd.DataFrame:
    formation = int(params["momentum_days"])
    window = int(params["dispersion_window"])
    risk_off_z = float(params["risk_off_z"])
    universe = rolling_liquidity_universe(panel, max_assets=15)
    rets = panel.returns
    dispersion = rets.std(axis=1, ddof=0).rolling(window, min_periods=max(5, window // 3)).mean().shift(1)
    mean = dispersion.rolling(252, min_periods=60).mean()
    std = dispersion.rolling(252, min_periods=60).std(ddof=0).replace(0.0, np.nan)
    z = (dispersion - mean) / std
    risk_on = (z < risk_off_z).astype(float)
    mom = panel.close.pct_change(formation, fill_method=None).shift(1).where(universe)
    rank = mom.rank(axis=1, pct=True)
    signal = ((rank >= 0.8) & universe).astype(float).mul(risk_on, axis=0)
    return inverse_vol_weights(signal, rets)


def price_path_continuity(panel: ResearchPanel, params: dict) -> pd.DataFrame:
    formation = int(params["formation_days"])
    q = float(params["continuity_quantile"])
    universe = rolling_liquidity_universe(panel, max_assets=15)
    r = panel.returns
    total = panel.close.pct_change(formation, fill_method=None).shift(1)
    path = r.abs().rolling(formation, min_periods=formation).sum().shift(1).replace(0.0, np.nan)
    continuity = (total.abs() / path).where(total > 0).where(universe)
    threshold = continuity.quantile(q, axis=1)
    signal = continuity.ge(threshold, axis=0).astype(float).where(universe, 0.0)
    return inverse_vol_weights(signal, r)


def volatility_conditioned_reversal(panel: ResearchPanel, params: dict) -> pd.DataFrame:
    formation = int(params["formation_days"])
    vol_q = float(params["volatility_quantile"])
    skip = int(params["skip_days"])
    universe = rolling_liquidity_universe(panel, max_assets=15)
    r = panel.returns
    end = panel.close.shift(1 + skip)
    start = panel.close.shift(1 + skip + formation)
    past = end / start - 1.0
    vol = r.shift(1 + skip).rolling(formation, min_periods=formation).std()
    vol_threshold = vol.quantile(vol_q, axis=1)
    high_vol = vol.ge(vol_threshold, axis=0)
    loser_rank = past.where(universe & high_vol).rank(axis=1, pct=True, ascending=True)
    signal = ((loser_rank <= 0.2) & universe & high_vol).astype(float)
    return inverse_vol_weights(signal, r)


STRUCTURAL_ENGINES = {
    "time_series_momentum": time_series_momentum,
    "donchian_breakout": donchian_breakout,
    "cross_sectional_momentum": cross_sectional_momentum,
    "lagged_dispersion_momentum": lagged_dispersion_momentum,
    "price_path_continuity": price_path_continuity,
    "volatility_conditioned_reversal": volatility_conditioned_reversal,
}


def build_structural_weights(panel: ResearchPanel, family: str, params: dict) -> pd.DataFrame:
    try:
        fn = STRUCTURAL_ENGINES[family]
    except KeyError as exc:
        raise ValueError(f"unsupported structural family: {family}") from exc
    w = fn(panel, params)
    if (w < -1e-12).any(axis=None):
        raise ValueError("long/cash research engine produced short exposure")
    gross = w.sum(axis=1)
    if (gross > 1.000001).any():
        raise ValueError("gross exposure exceeded 1.0")
    return w
