from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import yaml


@dataclass(frozen=True)
class ResearchPanel:
    close: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    quote_volume: pd.DataFrame
    trade_count: pd.DataFrame
    research_end: pd.Timestamp
    holdout_start: pd.Timestamp

    @property
    def returns(self) -> pd.DataFrame:
        return self.close.pct_change(fill_method=None)


def _load_fold_boundaries(path: str | Path) -> tuple[pd.Timestamp, pd.Timestamp]:
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    research_end = pd.Timestamp(cfg["research_window"]["end"])
    holdout_start = pd.Timestamp(cfg["holdout"]["start"])
    if research_end.tzinfo is None:
        research_end = research_end.tz_localize("UTC")
    if holdout_start.tzinfo is None:
        holdout_start = holdout_start.tz_localize("UTC")
    if holdout_start <= research_end:
        raise ValueError("invalid research/holdout boundary")
    if cfg["holdout"].get("opened") is not False:
        raise ValueError("holdout is not sealed")
    return research_end, holdout_start


def load_research_panel(
    dataset_dir: str | Path,
    folds_path: str | Path,
    *,
    columns: Iterable[str] = ("close", "high", "low", "quote_volume", "trade_count"),
) -> ResearchPanel:
    """Load only rows in the research window; holdout values are never materialized.

    This function intentionally reads each CSV with a date predicate and discards
    all rows at or after the final holdout boundary before constructing any panel.
    """
    research_end, holdout_start = _load_fold_boundaries(folds_path)
    root = Path(dataset_dir) / "market"
    requested = list(columns)
    frames: dict[str, list[pd.Series]] = {name: [] for name in requested}

    for path in sorted(root.glob("*.csv")):
        usecols = ["timestamp", "symbol", "episode_id", *requested]
        df = pd.read_csv(path, usecols=usecols)
        ts = pd.to_datetime(df["timestamp"], utc=True, errors="raise")
        keep = ts <= research_end
        if not bool(keep.any()):
            continue
        df = df.loc[keep].copy()
        df.index = ts.loc[keep]
        market_id = path.stem
        for name in requested:
            s = pd.to_numeric(df[name], errors="coerce").rename(market_id)
            frames[name].append(s)

    panels: dict[str, pd.DataFrame] = {}
    for name, values in frames.items():
        if not values:
            raise ValueError(f"no research values for {name}")
        p = pd.concat(values, axis=1).sort_index()
        if not p.index.is_monotonic_increasing or p.index.has_duplicates:
            raise ValueError(f"invalid research index for {name}")
        if bool((p.index >= holdout_start).any()):
            raise RuntimeError("holdout row leaked into research panel")
        panels[name] = p

    return ResearchPanel(
        close=panels["close"], high=panels["high"], low=panels["low"],
        quote_volume=panels["quote_volume"], trade_count=panels["trade_count"],
        research_end=research_end, holdout_start=holdout_start,
    )


def rolling_liquidity_universe(
    panel: ResearchPanel,
    *,
    lookback_days: int = 30,
    max_assets: int = 15,
    min_median_notional: float = 10_000_000.0,
) -> pd.DataFrame:
    """Point-in-time liquid-universe mask using only lagged quote volume."""
    qv = panel.quote_volume.astype(float)
    med = qv.shift(1).rolling(lookback_days, min_periods=max(5, lookback_days // 3)).median()
    eligible = med >= float(min_median_notional)
    rank = med.where(eligible).rank(axis=1, ascending=False, method="first")
    return (rank <= int(max_assets)).fillna(False)


def inverse_vol_weights(raw_signal: pd.DataFrame, returns: pd.DataFrame, *, target_annual_vol: float = 0.12, max_asset_weight: float = 0.15) -> pd.DataFrame:
    vol = returns.shift(1).ewm(span=30, adjust=False, min_periods=20).std() * np.sqrt(365.0)
    score = raw_signal.clip(lower=0.0) / vol.replace(0.0, np.nan)
    score = score.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    denom = score.sum(axis=1).replace(0.0, np.nan)
    w = score.div(denom, axis=0).fillna(0.0).clip(upper=max_asset_weight)
    vol_upper = (w * vol.fillna(0.0)).sum(axis=1).replace(0.0, np.nan)
    scale = (float(target_annual_vol) / vol_upper).clip(upper=1.0).fillna(0.0)
    return w.mul(scale, axis=0)
