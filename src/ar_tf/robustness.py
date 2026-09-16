from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd


def parameter_grid_plateau(
    *,
    trials: list[dict[str, Any]],
    metric_by_trial: dict[str, float],
    winner_trial_id: str,
    tolerance: float = 0.15,
    min_neighbor_fraction: float = 0.60,
) -> dict[str, Any]:
    winner=next(t for t in trials if t['trial_id']==winner_trial_id)
    family=[t for t in trials if t['family']==winner['family']]
    best=float(metric_by_trial[winner_trial_id])
    neighbors=[]
    for t in family:
        if t['trial_id']==winner_trial_id: continue
        keys=set(winner['params'])|set(t['params'])
        diffs=sum(winner['params'].get(k)!=t['params'].get(k) for k in keys)
        if diffs==1: neighbors.append(t)
    values=[float(metric_by_trial[t['trial_id']]) for t in neighbors if np.isfinite(metric_by_trial.get(t['trial_id'],np.nan))]
    if best<=0 or len(values)<2:
        return {'passed':False,'winner_metric':best,'neighbor_count':len(values),'plateau_fraction':0.0}
    threshold=best*(1.0-tolerance)
    frac=float(np.mean(np.asarray(values)>=threshold))
    return {'passed':bool(frac>=min_neighbor_fraction),'winner_metric':best,'neighbor_count':len(values),'plateau_fraction':frac,'threshold':threshold}


def perturbation_suite(
    *,
    weights: pd.DataFrame,
    oos_index: pd.DatetimeIndex,
    run_fn: Callable[[pd.DataFrame, float], pd.Series],
    seed: int = 73,
) -> dict[str, Any]:
    scenarios={}
    for delay in (1,2):
        shifted=weights.shift(delay).fillna(0.0)
        r=run_fn(shifted,1.0).reindex(oos_index).fillna(0.0)
        scenarios[f'extra_delay_{delay}d']={'expectancy':float(r.mean()),'total_return':float((1.0+r).prod()-1.0)}
    rng=np.random.default_rng(seed)
    missed=weights.copy()
    positions=np.where(weights.index.isin(oos_index))[0]
    if len(positions):
        chosen=rng.choice(positions,size=max(1,int(round(len(positions)*0.05))),replace=False)
        for pos in np.sort(chosen):
            if pos>0: missed.iloc[pos]=missed.iloc[pos-1]
    r=run_fn(missed,1.0).reindex(oos_index).fillna(0.0)
    scenarios['missed_rebalance_5pct']={'expectancy':float(r.mean()),'total_return':float((1.0+r).prod()-1.0)}
    r2=run_fn(weights,2.0).reindex(oos_index).fillna(0.0)
    r3=run_fn(weights,3.0).reindex(oos_index).fillna(0.0)
    scenarios['cost_2x']={'expectancy':float(r2.mean()),'total_return':float((1.0+r2).prod()-1.0)}
    scenarios['cost_3x']={'expectancy':float(r3.mean()),'total_return':float((1.0+r3).prod()-1.0)}
    core=[scenarios['extra_delay_1d'],scenarios['extra_delay_2d'],scenarios['missed_rebalance_5pct'],scenarios['cost_2x']]
    passed=all(x['expectancy']>0 and x['total_return']>0 for x in core)
    return {'passed':bool(passed),'scenarios':scenarios,'severe_cost_is_break_test':True}


def regime_decomposition(
    *,
    returns: pd.Series,
    btc_returns: pd.Series,
    cross_sectional_returns: pd.DataFrame,
    aggregate_liquidity: pd.Series,
) -> dict[str, Any]:
    r=returns.dropna().astype(float)
    btc=btc_returns.reindex(r.index).fillna(0.0)
    price=(1.0+btc).cumprod(); slow=price.ewm(span=200,adjust=False).mean()
    market=pd.Series('SIDEWAYS',index=r.index,dtype='object')
    market.loc[price>slow*1.03]='BULL'; market.loc[price<slow*0.97]='BEAR'
    vol=btc.rolling(30,min_periods=20).std().shift(1)
    vol_state=pd.Series(np.where(vol>=vol.median(),'HIGH_VOL','LOW_VOL'),index=r.index)
    liq=aggregate_liquidity.reindex(r.index).shift(1)
    liq_state=pd.Series(np.where(liq>=liq.median(),'HIGH_LIQUIDITY','LOW_LIQUIDITY'),index=r.index)
    dispersion=cross_sectional_returns.reindex(r.index).std(axis=1,ddof=0).shift(1)
    disp_state=pd.Series(np.where(dispersion>=dispersion.median(),'HIGH_DISPERSION','LOW_DISPERSION'),index=r.index)

    def summarize(groups: pd.Series):
        out={}
        for name,g in pd.concat([r.rename('r'),groups.rename('g')],axis=1).dropna().groupby('g'):
            out[str(name)]={'n':int(len(g)),'mean':float(g['r'].mean()),'total_return':float((1.0+g['r']).prod()-1.0)}
        return out
    by_year={str(y):{'n':int(len(g)),'mean':float(g.mean()),'total_return':float((1.0+g).prod()-1.0)} for y,g in r.groupby(r.index.year)}
    breakdown={'calendar_year':by_year,'market_regime':summarize(market),'volatility':summarize(vol_state),'liquidity':summarize(liq_state),'dispersion':summarize(disp_state)}
    segment_means=[v['mean'] for section in ('market_regime','volatility','liquidity','dispersion') for v in breakdown[section].values() if v['n']>=20]
    year_returns=[v['total_return'] for v in by_year.values() if v['n']>=60]
    positive_segment_fraction=float(np.mean(np.asarray(segment_means)>0)) if segment_means else 0.0
    positive_year_fraction=float(np.mean(np.asarray(year_returns)>0)) if year_returns else 0.0
    catastrophic=any(x<=-0.002 for x in segment_means)
    passed=bool(positive_segment_fraction>=0.60 and positive_year_fraction>=0.60 and not catastrophic)
    return {'passed':passed,'positive_segment_fraction':positive_segment_fraction,'positive_year_fraction':positive_year_fraction,'breakdown':breakdown}


def capacity_gate(capacity: dict[str, Any], *, minimum_research_capacity_usd: float = 100_000.0) -> dict[str, Any]:
    p05=capacity.get('p05_capacity_usd')
    turnover=capacity.get('p95_one_way_turnover')
    passed=bool(p05 is not None and float(p05)>=minimum_research_capacity_usd and turnover is not None and float(turnover)<=1.0)
    return {'passed':passed,'minimum_research_capacity_usd':minimum_research_capacity_usd,'p05_capacity_usd':p05,'p95_one_way_turnover':turnover,'method':capacity.get('method'),'requires_recertification_for_scaled_live':True}
