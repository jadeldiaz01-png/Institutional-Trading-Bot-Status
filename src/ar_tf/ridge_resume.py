from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .classical_tournament import _oos_index, _run, run_ridge_stage
from .ml_trials import prediction_to_weights, walk_forward_predictions

RIDGE_SHARDS=((0,9),(9,18),(18,27))


def ridge_trials(registry: dict[str,Any]) -> list[dict[str,Any]]:
    trials=[t for t in registry['trials'] if t['family']=='ridge']
    if len(trials)!=27 or len({t['trial_id'] for t in trials})!=27:
        raise ValueError('expected exactly 27 unique preregistered ridge trials')
    return trials


def shard_trial_ids(registry: dict[str,Any], shard: int) -> list[str]:
    if shard not in (0,1,2): raise ValueError('shard must be 0, 1, or 2')
    a,b=RIDGE_SHARDS[shard]
    return [t['trial_id'] for t in ridge_trials(registry)[a:b]]


def execute_shard(*,panel,registry,folds_path,shard:int) -> dict[str,Any]:
    oos=_oos_index(panel,folds_path); trials=ridge_trials(registry)
    wanted=set(shard_trial_ids(registry,shard)); selected=[t for t in trials if t['trial_id'] in wanted]
    cache={}; base={}; stressed={}; severe={}; failures=[]
    for trial in selected:
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
    return {'shard':shard,'trial_ids':[t['trial_id'] for t in selected],'failures':failures,'base':pd.DataFrame(base,index=oos),'stressed':pd.DataFrame(stressed,index=oos),'severe':pd.DataFrame(severe,index=oos)}


def _sha(path:Path)->str: return hashlib.sha256(path.read_bytes()).hexdigest()


def write_shard(result:dict[str,Any],root:Path,lineage:dict[str,str])->None:
    root.mkdir(parents=True,exist_ok=True)
    for key,name in [('base','base.csv'),('stressed','stressed.csv'),('severe','severe.csv')]: result[key].to_csv(root/name)
    m={'schema_version':'1.0.0','stage':'RIDGE_SHARD','shard':result['shard'],'trial_ids':result['trial_ids'],'trial_count':len(result['trial_ids']),'failures':result['failures'],'holdout_opened':False,'holdout_evaluated':False,**lineage}
    m.update({f'{k}_sha256':_sha(root/f'{k}.csv') for k in ('base','stressed','severe')})
    (root/'manifest.json').write_text(json.dumps(m,sort_keys=True,indent=2)+'\n')


def load_shard(root:Path)->dict[str,Any]:
    m=json.loads((root/'manifest.json').read_text())
    for k in ('base','stressed','severe'):
        if _sha(root/f'{k}.csv')!=m[f'{k}_sha256']: raise ValueError(f'tampered ridge shard {k}')
    return {'manifest':m,**{k:pd.read_csv(root/f'{k}.csv',index_col=0,parse_dates=True) for k in ('base','stressed','severe')}}


def validate_shards(registry:dict[str,Any],shards:list[dict[str,Any]])->tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame]:
    if len(shards)!=3: raise ValueError('exactly three ridge shards required')
    shards=sorted(shards,key=lambda x:int(x['manifest']['shard']))
    if [s['manifest']['shard'] for s in shards]!=[0,1,2]: raise ValueError('shards must be 0,1,2 exactly once')
    lineage=('parent_checkpoint_sha256','dataset_sha256','registry_sha256','folds_sha256')
    for k in lineage:
        if len({s['manifest'][k] for s in shards})!=1: raise ValueError(f'lineage mismatch: {k}')
    expected=[t['trial_id'] for t in ridge_trials(registry)]; observed=sum((s['manifest']['trial_ids'] for s in shards),[])
    if len(observed)!=27 or len(set(observed))!=27 or set(observed)!=set(expected): raise ValueError('ridge 27/27 exactly-once violation')
    for i,s in enumerate(shards):
        if s['manifest']['trial_ids']!=shard_trial_ids(registry,i) or s['manifest']['trial_count']!=9: raise ValueError('ridge shard partition mismatch')
        if s['manifest'].get('holdout_opened') or s['manifest'].get('holdout_evaluated'): raise ValueError('holdout governance violation')
    frames=[]
    for k in ('base','stressed','severe'):
        f=pd.concat([s[k] for s in shards],axis=1)
        if list(f.columns)!=expected: raise ValueError('deterministic ridge column order mismatch')
        frames.append(f)
    return tuple(frames)


def reduce_and_adjudicate(*,panel,registry,folds_path,structural_base,structural_stressed,structural_severe,shards):
    rb,rs,rv=validate_shards(registry,shards)
    # Reuse the frozen statistical implementation without changing thresholds: inject the
    # already-computed 27 predictions by temporarily presenting them as the Ridge outputs
    # is intentionally NOT allowed. Reducer therefore emits evidence only; adjudication
    # remains a separate deterministic step once equivalence is certified.
    return {'schema_version':'1.0.0','stage':'RIDGE_REDUCER','ridge_trial_count':27,'trial_count_total':149,'holdout_opened':False,'holdout_evaluated':False,'paper_authorized':False,'testnet_authorized':False,'live_authorized':False,'decision':'RIDGE_27_REDUCED_PENDING_EQUIVALENCE','ridge_base':rb,'ridge_stressed':rs,'ridge_severe':rv}
