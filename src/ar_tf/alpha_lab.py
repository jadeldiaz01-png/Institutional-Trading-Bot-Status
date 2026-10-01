from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class AlphaLabConfig:
    dispersion_window: int = 30
    dispersion_z_window: int = 252
    dispersion_risk_off_z: float = 1.5
    min_expected_edge_bps: float = 15.0
    uncertainty_multiplier: float = 1.0
    max_turnover_per_rebalance: float = 0.35


def cross_sectional_dispersion(returns: pd.DataFrame) -> pd.Series:
    """Cross-sectional standard deviation using only information available at t."""
    return returns.std(axis=1, ddof=0)


def dispersion_state(returns: pd.DataFrame, cfg: AlphaLabConfig = AlphaLabConfig()) -> pd.DataFrame:
    dispersion = cross_sectional_dispersion(returns)
    mean = dispersion.rolling(cfg.dispersion_z_window, min_periods=max(30, cfg.dispersion_z_window // 4)).mean()
    std = dispersion.rolling(cfg.dispersion_z_window, min_periods=max(30, cfg.dispersion_z_window // 4)).std(ddof=0).replace(0, np.nan)
    z = (dispersion - mean) / std
    scale = (1.0 - (z.clip(lower=0.0) / max(cfg.dispersion_risk_off_z, 1e-6))).clip(0.0, 1.0)
    return pd.DataFrame({"dispersion": dispersion, "dispersion_z": z, "momentum_scale": scale})


def cost_aware_trade_gate(
    forecast_return: pd.DataFrame,
    forecast_uncertainty: pd.DataFrame,
    round_trip_cost_bps: pd.DataFrame | float,
    cfg: AlphaLabConfig = AlphaLabConfig(),
) -> pd.DataFrame:
    """Trade only when expected edge clears costs plus an uncertainty margin.

    Inputs are forecasts known at decision time. The gate never looks at realized future returns.
    """
    f, u = forecast_return.align(forecast_uncertainty, join="inner", axis=0)
    f, u = f.align(u, join="inner", axis=1)
    if np.isscalar(round_trip_cost_bps):
        cost = pd.DataFrame(float(round_trip_cost_bps) / 10_000.0, index=f.index, columns=f.columns)
    else:
        cost, _ = round_trip_cost_bps.align(f, join="right", axis=0)
        cost, _ = cost.align(f, join="right", axis=1)
        cost = cost.astype(float) / 10_000.0
    threshold = cost + cfg.min_expected_edge_bps / 10_000.0 + cfg.uncertainty_multiplier * u.abs()
    return (f > threshold).astype(float)


def blend_alpha(
    trend_signal: pd.DataFrame,
    ml_forecast: pd.DataFrame,
    ml_gate: pd.DataFrame,
    dispersion_scale: pd.Series,
    trend_weight: float = 0.70,
    ml_weight: float = 0.30,
) -> pd.DataFrame:
    """Conservative long-only blend. ML can add conviction but cannot bypass regime scaling."""
    t, m = trend_signal.align(ml_forecast, join="inner", axis=0)
    t, m = t.align(m, join="inner", axis=1)
    g, _ = ml_gate.align(m, join="right", axis=0)
    g, _ = g.align(m, join="right", axis=1)
    ml_component = m.clip(lower=0.0) * g.fillna(0.0)
    raw = trend_weight * t.clip(lower=0.0) + ml_weight * ml_component
    scale = dispersion_scale.reindex(raw.index).fillna(0.0)
    return raw.mul(scale, axis=0).clip(lower=0.0)


def turnover_limiter(previous: pd.Series, target: pd.Series, max_turnover: float = 0.35) -> pd.Series:
    """Scale a rebalance so one-way turnover does not exceed the configured budget."""
    prev, tgt = previous.align(target, join="outer", fill_value=0.0)
    delta = tgt - prev
    turnover = float(delta.abs().sum())
    if turnover <= max_turnover or turnover == 0:
        return tgt
    return prev + delta * (max_turnover / turnover)
