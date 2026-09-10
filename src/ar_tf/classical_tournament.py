from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from .advanced_validation import paired_block_bootstrap_superiority, white_reality_check
from .backtest import CostModel, run_backtest
from .ml_trials import prediction_to_weights, walk_forward_predictions
from .research_panel import ResearchPanel, rolling_liquidity_universe
from .spa_validation import hansen_spa
from .validation import deflated_sharpe_probability, expected_max_sharpe, performance_metrics, probability_of_backtest_overfitting


def _oos_index(panel: ResearchPanel, folds_path: str | Path) -> pd.DatetimeIndex:
    cfg=yaml.safe_load(Path(folds_path).read_text(encoding='utf-8'))
    idx=pd.DatetimeIndex([],tz='UTC')
    for fold in cfg['walk_forward']['folds']:
        s=pd.Timestamp(fold['test_start'],tz='UTC'); e=pd.Timestamp(fold['test_end'],tz='UTC')
        idx=idx.union(panel.close.index[(panel.close.index>=s)&(panel.close.index<=e)])
    return idx.sort_values()


def _run(panel: ResearchPanel, w: pd.DataFrame, multiplier: float) -> pd.Series:
    return run_backtest(panel.returns,w,CostModel(),cost_multiplier=multiplier,missing_held_asset_return=-0.25)['net_return']


def _benchmark(panel: ResearchPanel, oos: pd.DatetimeIndex) -> pd.Series:
    u=rolling_liquidity_universe(panel,max_assets=15)
    w=u.astype(float).div(u.sum(axis=1).replace(0,np.nan),axis=0).fillna(0.0)
    return _run(panel,w,1.0).reindex(oos).fillna(0.0)


def run_ridge_stage(
    *, panel: ResearchPanel, registry: dict[str, Any], folds_path: str | Path,
    structural_base: pd.DataFrame, structural_stressed: pd.DataFrame, structural_severe: pd.DataFrame,
) -> dict[str, Any]:
    oos=_oos_index(panel,folds_path)
    ridge_trials=[t for t in registry['trials'] if t['family']=='ridge']
    if len(ridge_trials)!=27: raise ValueError(f'expected 27 ridge trials, got {len(ridge_trials)}')
    cache={}; base={}; stressed={}; severe={}; failures=[]
    for trial in ridge_trials:
        p=trial['params']; key=(float(p['alpha']),int(p['horizon_days']),int(trial['seed']))
        try:
            if key not in cache:
                cache[key]=walk_forward_predictions(panel,folds_path,family='ridge',params=p,seed=int(trial['seed']),max_training_rows_per_fold=100_000)
            w=prediction_to_weights(panel,cache[key],cost_gate_bps=float(p['cost_gate_bps']))
            base[trial['trial_id']]=_run(panel,w,1.0).reindex(oos).fillna(0.0)
            stressed[trial['trial_id']]=_run(panel,w,2.0).reindex(oos).fillna(0.0)
            severe[trial['trial_id']]=_run(panel,w,3.0).reindex(oos).fillna(0.0)
        except Exception as exc:
            failures.append({'trial_id':trial['trial_id'],'error':type(exc).__name__,'message':str(exc)})
            z=pd.Series(0.0,index=oos); base[trial['trial_id']]=z; stressed[trial['trial_id']]=z; severe[trial['trial_id']]=z

    rb=pd.DataFrame(base,index=oos).fillna(0.0); rs=pd.DataFrame(stressed,index=oos).fillna(0.0); rv=pd.DataFrame(severe,index=oos).fillna(0.0)
    sb=structural_base.reindex(oos).fillna(0.0); ss=structural_stressed.reindex(oos).fillna(0.0); sv=structural_severe.reindex(oos).fillna(0.0)
    combined=pd.concat([sb,rb],axis=1); combined_stress=pd.concat([ss,rs],axis=1); combined_severe=pd.concat([sv,rv],axis=1)
    if combined.shape[1]!=149: raise ValueError(f'expected 149 combined trials, got {combined.shape[1]}')

    metrics={c:performance_metrics(combined[c]) for c in combined.columns}
    expected=expected_max_sharpe([m['sharpe'] for m in metrics.values()])
    dsr={c:deflated_sharpe_probability(metrics[c]['sharpe'],len(combined),float(combined[c].skew()),float(combined[c].kurtosis()+3.0),expected) for c in combined.columns}
    pbo=probability_of_backtest_overfitting(combined,slices=8)
    bench=_benchmark(panel,oos)
    white=white_reality_check(combined,bench); spa=hansen_spa(combined,bench)
    winner=sorted(combined.columns,key=lambda c:(dsr[c],metrics[c]['sharpe'],metrics[c]['expectancy']),reverse=True)[0]
    superiority=paired_block_bootstrap_superiority(combined[winner],bench)
    stress_metrics=performance_metrics(combined_stress[winner])
    cost_ok=bool(metrics[winner]['expectancy']>0 and stress_metrics['expectancy']>0 and metrics[winner]['total_return']>0 and stress_metrics['total_return']>0)
    statistical_ok=bool(dsr[winner]>=0.95 and np.isfinite(pbo.get('pbo',np.nan)) and pbo['pbo']<=0.20 and white.get('passed') and spa.get('passed') and superiority.get('passed'))
    winner_is_ridge=winner in rb.columns
    admit_gbm=bool(statistical_ok and cost_ok)
    return {
        'schema_version':'1.0.0','stage':'RIDGE_CHALLENGER','trial_count_total':149,'ridge_trial_count':27,'ridge_failures':failures,
        'winner':winner,'winner_is_ridge':winner_is_ridge,'winner_metrics':metrics[winner],'winner_dsr_probability':dsr[winner],
        'pbo':pbo,'white_reality_check':white,'hansen_spa':spa,'paired_superiority':superiority,
        'base_and_stressed_cost_survival':cost_ok,'gradient_boosting_admitted':admit_gbm,
        'holdout_opened':False,'holdout_evaluated':False,'paper_authorized':False,'testnet_authorized':False,'live_authorized':False,
        'decision':'ADMIT_GRADIENT_BOOSTING' if admit_gbm else 'NO_EDGE_VERIFIED',
        'combined_base':combined,'combined_stressed':combined_stress,'combined_severe':combined_severe,
    }


def write_ridge_stage(result: dict[str, Any], output_dir: str | Path) -> None:
    root=Path(output_dir); root.mkdir(parents=True,exist_ok=True)
    s=dict(result); b=s.pop('combined_base'); st=s.pop('combined_stressed'); sv=s.pop('combined_severe')
    b.to_csv(root/'combined-149-oos-base.csv'); st.to_csv(root/'combined-149-oos-stressed.csv'); sv.to_csv(root/'combined-149-oos-severe.csv')
    (root/'ridge-stage.json').write_text(json.dumps(s,indent=2,sort_keys=True,default=lambda x: float(x) if isinstance(x,np.generic) else str(x))+'\n',encoding='utf-8')
