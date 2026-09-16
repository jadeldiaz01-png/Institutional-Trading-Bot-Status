from __future__ import annotations

import numpy as np
import pandas as pd


def lagged_return(close: pd.DataFrame, k: int) -> pd.DataFrame:
    if k < 1:
        raise ValueError('k must be >= 1')
    return close.shift(1) / close.shift(1 + k) - 1.0


def rolling_autocorr_1(returns: pd.DataFrame, window: int) -> pd.DataFrame:
    if window < 3:
        raise ValueError('window must be >= 3')
    x = returns.shift(1)
    return x.rolling(window).corr(x.shift(1))


def sign_persistence(returns: pd.DataFrame, window: int) -> pd.DataFrame:
    if window < 2:
        raise ValueError('window must be >= 2')
    s = np.sign(returns.shift(1))
    same = (s == s.shift(1)).astype(float)
    return same.rolling(window).mean()


def path_efficiency(close: pd.DataFrame, lookback: int) -> pd.DataFrame:
    if lookback < 2:
        raise ValueError('lookback must be >= 2')
    c = close.shift(1)
    net = (c - c.shift(lookback)).abs()
    gross = c.diff().abs().rolling(lookback).sum()
    return (net / gross.replace(0.0, np.nan)).clip(0.0, 1.0)


def directional_consistency(returns: pd.DataFrame, lookback: int) -> pd.DataFrame:
    if lookback < 2:
        raise ValueError('lookback must be >= 2')
    s = np.sign(returns.shift(1))
    return (s.rolling(lookback).sum().abs() / float(lookback)).clip(0.0, 1.0)


def donchian_breakout_features(
    close: pd.DataFrame,
    high: pd.DataFrame,
    low: pd.DataFrame,
    lookback: int,
    atr_window: int = 14,
) -> dict[str, pd.DataFrame]:
    if lookback < 2 or atr_window < 2:
        raise ValueError('lookback and atr_window must be >= 2')
    c = close.shift(1)
    h = high.shift(1)
    l = low.shift(1)
    previous_level = high.shift(2).rolling(lookback).max()
    prev_close = close.shift(2)
    tr = pd.DataFrame(
        np.maximum.reduce([
            (h - l).to_numpy(),
            (h - prev_close).abs().to_numpy(),
            (l - prev_close).abs().to_numpy(),
        ]),
        index=close.index,
        columns=close.columns,
    )
    atr = tr.rolling(atr_window).mean().replace(0.0, np.nan)
    return {
        'breakout_flag': (c > previous_level).astype(float),
        'donchian_distance': c / previous_level - 1.0,
        'breakout_strength_atr': (c - previous_level) / atr,
        'retest_distance_atr': (l - previous_level) / atr,
    }


def realized_volatility(returns: pd.DataFrame, window: int, annualization: float = 365.0) -> pd.DataFrame:
    if window < 2:
        raise ValueError('window must be >= 2')
    return returns.shift(1).rolling(window).std() * np.sqrt(float(annualization))


def lagged_liquidity_rank(quote_volume: pd.DataFrame, window: int = 30) -> pd.DataFrame:
    if window < 2:
        raise ValueError('window must be >= 2')
    med = quote_volume.shift(1).rolling(window, min_periods=max(2, window // 3)).median()
    return med.rank(axis=1, pct=True)


def order_flow_imbalance_l1(events: pd.DataFrame) -> pd.Series:
    required = {'bid_price', 'bid_size', 'ask_price', 'ask_size'}
    missing = required - set(events.columns)
    if missing:
        raise ValueError(f'missing L1 columns: {sorted(missing)}')
    if 'timestamp' not in events.columns and not isinstance(events.index, pd.DatetimeIndex):
        raise ValueError('exchange timestamp is required')
    b = events['bid_price'].astype(float)
    bs = events['bid_size'].astype(float)
    a = events['ask_price'].astype(float)
    ass = events['ask_size'].astype(float)
    bp = b.shift(1); bsp = bs.shift(1); ap = a.shift(1); asp = ass.shift(1)
    bid_event = (b >= bp).astype(float) * bs - (b <= bp).astype(float) * bsp
    ask_event = (a <= ap).astype(float) * ass - (a >= ap).astype(float) * asp
    ofi = bid_event - ask_event
    return ofi.rename('ofi_l1')


def trade_imbalance(trades: pd.DataFrame) -> pd.Series:
    required = {'aggressor_side', 'quantity'}
    missing = required - set(trades.columns)
    if missing:
        raise ValueError(f'missing trade columns: {sorted(missing)}')
    side = trades['aggressor_side'].astype(str).str.upper()
    if not side.isin(['BUY', 'SELL']).all():
        raise ValueError('aggressor_side must be BUY or SELL from certified trade data')
    q = trades['quantity'].astype(float)
    signed = np.where(side.eq('BUY'), q, -q)
    denom = q.abs().sum()
    if denom <= 0:
        return pd.Series([np.nan], name='trade_imbalance')
    return pd.Series([float(np.sum(signed) / denom)], name='trade_imbalance')
