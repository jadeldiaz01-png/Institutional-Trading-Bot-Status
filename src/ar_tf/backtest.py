from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CostModel:
    taker_fee_bps: float = 10.0
    half_spread_bps: float = 2.0
    slippage_bps: float = 3.0

    def one_way_rate(self, multiplier: float = 1.0) -> float:
        return (self.taker_fee_bps + self.half_spread_bps + self.slippage_bps) * multiplier / 10_000.0


def validate_point_in_time(frame: pd.DataFrame) -> None:
    if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
        raise ValueError("timestamps must be unique and increasing")
    if frame.isna().all(axis=None):
        raise ValueError("dataset has no usable values")


def run_backtest(
    returns: pd.DataFrame,
    target_weights: pd.DataFrame,
    costs: CostModel = CostModel(),
    cost_multiplier: float = 1.0,
    missing_held_asset_return: float = 0.0,
) -> pd.DataFrame:
    """Close-to-close research simulation with one-bar delayed execution.

    ``missing_held_asset_return`` is a conservative terminal/data-loss stress.
    It applies only where an effective non-zero position exists but that market's
    return is missing. Missing returns for assets with zero exposure remain zero.
    A value such as -0.25 prevents a delisted/disappeared market from being
    silently treated as risk-free cash after the last observed bar.
    """
    if not -1.0 <= missing_held_asset_return <= 0.0:
        raise ValueError("missing_held_asset_return must be between -1 and 0")
    validate_point_in_time(returns)
    validate_point_in_time(target_weights)
    r, w = returns.align(target_weights, join="inner", axis=0)
    r, w = r.align(w, join="inner", axis=1)
    executed_w = w.shift(1).fillna(0.0)
    realized = r.copy()
    missing_with_position = realized.isna() & executed_w.ne(0.0)
    realized = realized.fillna(0.0)
    if missing_held_asset_return != 0.0:
        realized = realized.mask(missing_with_position, float(missing_held_asset_return))
    gross = (executed_w * realized).sum(axis=1)
    turnover = executed_w.diff().abs().sum(axis=1).fillna(executed_w.abs().sum(axis=1))
    trading_cost = turnover * costs.one_way_rate(cost_multiplier)
    net = gross - trading_cost
    equity = (1.0 + net).cumprod()
    return pd.DataFrame({
        "gross_return": gross,
        "turnover": turnover,
        "trading_cost": trading_cost,
        "missing_held_positions": missing_with_position.sum(axis=1).astype(float),
        "net_return": net,
        "equity": equity,
    })


def walk_forward_splits(index: pd.DatetimeIndex, train_days: int = 730, test_days: int = 180, step_days: int = 90, embargo_days: int = 7):
    start = index.min()
    end = index.max()
    cursor = start + pd.Timedelta(days=train_days)
    while cursor + pd.Timedelta(days=embargo_days + test_days) <= end:
        train_start = cursor - pd.Timedelta(days=train_days)
        train_end = cursor
        test_start = train_end + pd.Timedelta(days=embargo_days)
        test_end = test_start + pd.Timedelta(days=test_days)
        yield index[(index >= train_start) & (index < train_end)], index[(index >= test_start) & (index < test_end)]
        cursor += pd.Timedelta(days=step_days)
