from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ResearchConfig:
    momentum_days: tuple[int, ...] = (7, 30, 90, 180)
    ema_fast_days: int = 50
    ema_slow_days: int = 200
    donchian_days: int = 55
    vol_days: int = 30
    target_annual_vol: float = 0.12
    max_asset_weight: float = 0.15
    max_gross_exposure: float = 1.0
    trend_threshold: float = 0.25
    stress_vol_z: float = 2.0


def _zscore(s: pd.Series, window: int = 252) -> pd.Series:
    mean = s.rolling(window, min_periods=max(20, window // 4)).mean()
    std = s.rolling(window, min_periods=max(20, window // 4)).std(ddof=0).replace(0, np.nan)
    return ((s - mean) / std).clip(-5, 5)


def build_features(df: pd.DataFrame, cfg: ResearchConfig = ResearchConfig()) -> pd.DataFrame:
    required = {"close", "high", "low", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    x = df.sort_index().copy()
    logret = np.log(x["close"]).diff()
    x["ret_1d"] = logret
    for d in cfg.momentum_days:
        x[f"mom_{d}d"] = np.log(x["close"] / x["close"].shift(d))
        x[f"mom_{d}d_z"] = _zscore(x[f"mom_{d}d"])
    x["ema_fast"] = x["close"].ewm(span=cfg.ema_fast_days, adjust=False).mean()
    x["ema_slow"] = x["close"].ewm(span=cfg.ema_slow_days, adjust=False).mean()
    x["ema_trend"] = x["ema_fast"] / x["ema_slow"] - 1.0
    x["donchian_high"] = x["high"].shift(1).rolling(cfg.donchian_days).max()
    x["donchian_breakout"] = (x["close"] > x["donchian_high"]).astype(float)
    x["ann_vol"] = logret.ewm(span=cfg.vol_days, adjust=False).std() * np.sqrt(365)
    x["vol_z"] = _zscore(x["ann_vol"], window=365)
    x["notional"] = x["close"] * x["volume"]
    return x


def classify_regime(features: pd.DataFrame, cfg: ResearchConfig = ResearchConfig()) -> pd.Series:
    trend = features["ema_trend"]
    stress = features["vol_z"] >= cfg.stress_vol_z
    up = trend > 0
    down = trend < 0
    regime = pd.Series("SIDEWAYS", index=features.index, dtype="object")
    regime.loc[up] = "TREND_UP"
    regime.loc[down] = "TREND_DOWN"
    regime.loc[stress] = "HIGH_VOL_STRESS"
    return regime


def build_signal(features: pd.DataFrame, cfg: ResearchConfig = ResearchConfig()) -> pd.Series:
    mom_cols = [f"mom_{d}d_z" for d in cfg.momentum_days]
    momentum = features[mom_cols].mean(axis=1)
    trend_confirm = (features["ema_trend"] > 0).astype(float)
    breakout = features["donchian_breakout"].fillna(0.0)
    regime = classify_regime(features, cfg)
    regime_gate = regime.eq("TREND_UP").astype(float)
    strength_gate = (momentum >= cfg.trend_threshold).astype(float)
    raw = (0.75 * momentum + 0.25 * breakout) * trend_confirm * regime_gate * strength_gate
    return raw.clip(lower=0.0)


def portfolio_weights(signals: pd.Series, annual_vol: pd.Series, cfg: ResearchConfig = ResearchConfig()) -> pd.Series:
    """Conservative inverse-risk allocation with an effective volatility target.

    Without a covariance matrix we cannot estimate exact portfolio volatility.
    We therefore use the perfect-positive-correlation upper bound
    ``sum(w_i * sigma_i)`` and scale gross exposure so that this bound does not
    exceed ``target_annual_vol``. This is deliberately conservative and avoids
    silently ignoring the configured volatility target.
    """
    aligned = pd.concat([signals.rename("signal"), annual_vol.rename("vol")], axis=1).dropna()
    aligned = aligned[(aligned["vol"] > 0) & np.isfinite(aligned["vol"])]
    if aligned.empty:
        return pd.Series(dtype=float)
    inv_risk = aligned["signal"].clip(lower=0) / aligned["vol"].clip(lower=1e-6)
    if inv_risk.sum() <= 0:
        return pd.Series(0.0, index=aligned.index)

    # First create relative risk weights, then enforce single-name caps.
    w = inv_risk / inv_risk.sum()
    w = w.clip(upper=cfg.max_asset_weight)
    if w.sum() <= 0:
        return pd.Series(0.0, index=aligned.index)

    # Perfect-correlation volatility upper bound at current gross exposure.
    vol_upper_bound = float((w * aligned.loc[w.index, "vol"]).sum())
    if not np.isfinite(vol_upper_bound) or vol_upper_bound <= 0:
        return pd.Series(0.0, index=w.index)

    target_scale = min(1.0, cfg.target_annual_vol / vol_upper_bound)
    w *= target_scale

    gross = float(w.sum())
    if gross > cfg.max_gross_exposure:
        w *= cfg.max_gross_exposure / gross
    return w
