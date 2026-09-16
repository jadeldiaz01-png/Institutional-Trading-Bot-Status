from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class EdgeDecayPolicy:
    short_window: int = 30
    long_window: int = 180
    min_short_expectancy: float = 0.0
    min_short_sharpe: float = 0.0
    max_cost_ratio: float = 0.50
    max_turnover_ratio: float = 2.0
    page_hinkley_delta: float = 0.0
    page_hinkley_lambda: float = 0.03
    consecutive_breach_for_degraded: int = 2


def page_hinkley(values: pd.Series, *, delta: float = 0.0, threshold: float = 0.03) -> dict[str, Any]:
    x=values.dropna().astype(float)
    mean=0.0; cumulative=0.0; minimum=0.0; alarm=False; alarm_index=None
    for n,(idx,value) in enumerate(x.items(),start=1):
        mean += (value-mean)/n
        cumulative += value-mean-delta
        minimum=min(minimum,cumulative)
        if cumulative-minimum > threshold:
            alarm=True; alarm_index=str(idx); break
    return {"alarm":alarm,"alarm_index":alarm_index,"observations":int(len(x)),"threshold":float(threshold)}


def edge_health(
    net_returns: pd.Series,
    costs: pd.Series,
    turnover: pd.Series,
    benchmark_returns: pd.Series | None = None,
    *,
    policy: EdgeDecayPolicy = EdgeDecayPolicy(),
) -> dict[str, Any]:
    frame=pd.concat([net_returns.rename('r'),costs.rename('cost'),turnover.rename('turnover')],axis=1).dropna()
    if len(frame) < policy.long_window:
        return {"state":"INSUFFICIENT_FORWARD_EVIDENCE","automatic_promotion":False,"risk_reduction_required":False}
    short=frame.iloc[-policy.short_window:]
    long=frame.iloc[-policy.long_window:]
    sstd=float(short['r'].std(ddof=1))
    short_sharpe=float(np.sqrt(365)*short['r'].mean()/sstd) if sstd>0 else float('nan')
    short_expectancy=float(short['r'].mean())
    gross_proxy=float((short['r']+short['cost']).abs().sum())
    cost_ratio=float(short['cost'].abs().sum()/gross_proxy) if gross_proxy>0 else float('inf')
    long_turn=float(long['turnover'].median())
    short_turn=float(short['turnover'].median())
    turnover_ratio=float(short_turn/long_turn) if long_turn>0 else float('inf')
    residual=short['r']
    corr=None
    if benchmark_returns is not None:
        pair=pd.concat([net_returns.rename('r'),benchmark_returns.rename('b')],axis=1).dropna().iloc[-policy.short_window:]
        if len(pair)>2:
            corr=float(pair['r'].corr(pair['b']))
    drift=page_hinkley(net_returns.iloc[-policy.long_window:],delta=policy.page_hinkley_delta,threshold=policy.page_hinkley_lambda)
    breaches=[]
    if not np.isfinite(short_sharpe) or short_sharpe < policy.min_short_sharpe: breaches.append('SHORT_SHARPE_DEGRADED')
    if short_expectancy <= policy.min_short_expectancy: breaches.append('SHORT_EXPECTANCY_NON_POSITIVE')
    if cost_ratio > policy.max_cost_ratio: breaches.append('COST_EDGE_COMPRESSION')
    if turnover_ratio > policy.max_turnover_ratio: breaches.append('TURNOVER_DRIFT')
    if drift['alarm']: breaches.append('CHANGE_POINT_ALARM')
    state='HEALTHY' if not breaches else ('DEGRADED' if len(breaches)>=policy.consecutive_breach_for_degraded else 'WATCH')
    return {
        "state":state,"breaches":breaches,"short_expectancy":short_expectancy,"short_sharpe":short_sharpe,
        "cost_ratio":cost_ratio,"turnover_ratio":turnover_ratio,"benchmark_correlation":corr,"page_hinkley":drift,
        "automatic_promotion":False,"risk_reduction_required":state=='DEGRADED',
        "required_action":"BLOCK_NEW_RISK_AND_REVIEW" if state=='DEGRADED' else "CONTINUE_MONITORING",
    }
