from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from .classical_tournament import _oos_index, _run, adjudicate_ridge_outputs
from .ml_trials import FoldCheckpointPause, prediction_to_weights, walk_forward_predictions

RIDGE_TRIAL_COUNT = 27


def ridge_trials(registry: dict[str, Any]) -> list[dict[str, Any]]:
    trials = [t for t in registry['trials'] if t['family'] == 'ridge']
    if len(trials) != RIDGE_TRIAL_COUNT or len({t['trial_id'] for t in trials}) != RIDGE_TRIAL_COUNT:
        raise ValueError('expected exactly 27 unique preregistered ridge trials')
    return trials


def trial_at(registry: dict[str, Any], index: int) -> dict[str, Any]:
    if index < 0 or index >= RIDGE_TRIAL_COUNT:
        raise ValueError('ridge trial index must be in [0, 26]')
    return ridge_trials(registry)[index]


def execute_trial(
    *,
    panel,
    registry,
    folds_path,
    index: int,
    checkpoint_root: str | Path | None = None,
    checkpoint_lineage: Mapping[str, Any] | None = None,
    pause_after_fold: int | None = None,
) -> dict[str, Any]:
    trial = trial_at(registry, index)
    oos = _oos_index(panel, folds_path)
    p = trial['params']; tid = trial['trial_id']; failure = None
    try:
        predictions = walk_forward_predictions(
            panel,
            folds_path,
            family='ridge',
            params=p,
            seed=int(trial['seed']),
            max_training_rows_per_fold=100_000,
            checkpoint_root=checkpoint_root,
            checkpoint_trial_id=tid if checkpoint_root is not None else None,
            checkpoint_lineage=checkpoint_lineage,
            pause_after_fold=pause_after_fold,
        )
        weights = prediction_to_weights(panel, predictions, cost_gate_bps=float(p['cost_gate_bps']))
        base = _run(panel, weights, 1.0).reindex(oos).fillna(0.0)
        stressed = _run(panel, weights, 2.0).reindex(oos).fillna(0.0)
        severe = _run(panel, weights, 3.0).reindex(oos).fillna(0.0)
    except FoldCheckpointPause:
        raise
    except Exception as exc:
        failure = {'trial_id': tid, 'error': type(exc).__name__, 'message': str(exc)}
        base = stressed = severe = pd.Series(0.0, index=oos)
    return {'index': index, 'trial_id': tid, 'seed': int(trial['seed']), 'failure': failure,
            'base': pd.DataFrame({tid: base}, index=oos), 'stressed': pd.DataFrame({tid: stressed}, index=oos), 'severe': pd.DataFrame({tid: severe}, index=oos)}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_trial(result: dict[str, Any], root: Path, lineage: dict[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for key in ('base', 'stressed', 'severe'): result[key].to_csv(root / f'{key}.csv')
    manifest = {'schema_version':'2.1.0','stage':'RIDGE_SINGLE_TRIAL','execution_status':'COMPLETED','index':result['index'],'trial_id':result['trial_id'],'seed':result['seed'],'failure':result['failure'],'holdout_opened':False,'holdout_evaluated':False,**lineage}
    manifest.update({f'{k}_sha256': _sha(root / f'{k}.csv') for k in ('base','stressed','severe')})
    (root/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    (root/'result.sha256').write_text(_sha(root/'manifest.json')+'  manifest.json\n',encoding='utf-8')


def load_trial(root: Path) -> dict[str, Any]:
    mp=root/'manifest.json'; m=json.loads(mp.read_text())
    if m.get('stage')!='RIDGE_SINGLE_TRIAL' or m.get('execution_status')!='COMPLETED': raise ValueError('ridge result is not a completed single-trial artifact')
    if _sha(mp)!=(root/'result.sha256').read_text().split()[0]: raise ValueError('tampered ridge trial manifest')
    frames={}
    for key in ('base','stressed','severe'):
        p=root/f'{key}.csv'
        if _sha(p)!=m[f'{key}_sha256']: raise ValueError(f'tampered ridge trial {key}')
        frames[key]=pd.read_csv(p,index_col=0,parse_dates=True)
    return {'manifest':m,**frames}


def validate_trials(registry: dict[str, Any], results: list[dict[str, Any]]) -> tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame,list[dict[str,Any]]]:
    if len(results)!=RIDGE_TRIAL_COUNT: raise ValueError('exactly 27 ridge trial artifacts required')
    expected=ridge_trials(registry); ids=[t['trial_id'] for t in expected]; by_id={}
    lineage=('parent_checkpoint_sha256','dataset_sha256','registry_sha256','folds_sha256','config_sha256')
    for r in results:
        m=r['manifest']; tid=m.get('trial_id')
        if m.get('execution_status')!='COMPLETED': raise ValueError('incomplete ridge trial artifact')
        if tid in by_id: raise ValueError('duplicate ridge trial artifact')
        if tid not in ids: raise ValueError('unknown ridge trial id')
        if m.get('holdout_opened') or m.get('holdout_evaluated'): raise ValueError('holdout governance violation')
        by_id[tid]=r
    if set(by_id)!=set(ids): raise ValueError('ridge 27/27 exactly-once violation')
    for key in lineage:
        values={r['manifest'].get(key) for r in results}
        if len(values)!=1 or next(iter(values)) in (None,''): raise ValueError(f'lineage mismatch: {key}')
    for i,t in enumerate(expected):
        m=by_id[t['trial_id']]['manifest']
        if m.get('index')!=i or int(m.get('seed'))!=int(t['seed']): raise ValueError('ridge preregistration identity mismatch')
    frames=[]
    for key in ('base','stressed','severe'):
        frame=pd.concat([by_id[tid][key] for tid in ids],axis=1)
        if list(frame.columns)!=ids: raise ValueError('deterministic ridge column order mismatch')
        frames.append(frame)
    failures=[by_id[tid]['manifest']['failure'] for tid in ids if by_id[tid]['manifest'].get('failure')]
    return frames[0],frames[1],frames[2],failures


def reduce_and_adjudicate(*,panel,registry,folds_path,structural_base,structural_stressed,structural_severe,results):
    base,stressed,severe,failures=validate_trials(registry,results)
    return adjudicate_ridge_outputs(panel=panel,folds_path=folds_path,structural_base=structural_base,structural_stressed=structural_stressed,structural_severe=structural_severe,ridge_base=base,ridge_stressed=stressed,ridge_severe=severe,ridge_failures=failures)
