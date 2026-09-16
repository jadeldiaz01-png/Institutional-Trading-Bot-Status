from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import sklearn
import yaml

from .classical_tournament import _oos_index, _run, adjudicate_ridge_outputs
from .ml_trials import prediction_to_weights, walk_forward_predictions
from .ridge_fold_resume import (
    EXPECTED_FOLDS_PER_TRIAL,
    load_committed_fold,
    sha256_file,
    validate_fold_inventory,
)

RIDGE_TRIAL_COUNT = 27
MAX_TRAINING_ROWS_PER_FOLD = 100_000


def ridge_trials(registry: dict[str, Any]) -> list[dict[str, Any]]:
    trials = [t for t in registry['trials'] if t['family'] == 'ridge']
    if len(trials) != RIDGE_TRIAL_COUNT or len({t['trial_id'] for t in trials}) != RIDGE_TRIAL_COUNT:
        raise ValueError('expected exactly 27 unique preregistered ridge trials')
    return trials


def trial_at(registry: dict[str, Any], index: int) -> dict[str, Any]:
    if index < 0 or index >= RIDGE_TRIAL_COUNT:
        raise ValueError('ridge trial index must be in [0, 26]')
    return ridge_trials(registry)[index]


def runtime_fingerprint() -> dict[str, str]:
    """Versions that may affect numerical/scientific reproducibility."""
    return {
        'python': platform.python_version(),
        'numpy': np.__version__,
        'pandas': pd.__version__,
        'scikit_learn': sklearn.__version__,
    }


def runtime_fingerprint_sha256() -> str:
    canonical=json.dumps(runtime_fingerprint(),sort_keys=True,separators=(',',':')).encode()
    return hashlib.sha256(canonical).hexdigest()


def execute_trial(*, panel, registry, folds_path, index: int) -> dict[str, Any]:
    """Frozen monolithic reference path retained for equivalence testing."""
    trial = trial_at(registry, index)
    oos = _oos_index(panel, folds_path)
    p = trial['params']; tid = trial['trial_id']; failure = None
    try:
        predictions = walk_forward_predictions(
            panel, folds_path, family='ridge', params=p, seed=int(trial['seed']),
            max_training_rows_per_fold=MAX_TRAINING_ROWS_PER_FOLD,
        )
        weights = prediction_to_weights(panel, predictions, cost_gate_bps=float(p['cost_gate_bps']))
        base = _run(panel, weights, 1.0).reindex(oos).fillna(0.0)
        stressed = _run(panel, weights, 2.0).reindex(oos).fillna(0.0)
        severe = _run(panel, weights, 3.0).reindex(oos).fillna(0.0)
    except Exception as exc:
        failure = {'trial_id': tid, 'error': type(exc).__name__, 'message': str(exc)}
        base = stressed = severe = pd.Series(0.0, index=oos)
    return {'index': index, 'trial_id': tid, 'seed': int(trial['seed']), 'failure': failure,
            'base': pd.DataFrame({tid: base}, index=oos), 'stressed': pd.DataFrame({tid: stressed}, index=oos), 'severe': pd.DataFrame({tid: severe}, index=oos)}


def _fold_count(folds_path: str | Path) -> int:
    cfg=yaml.safe_load(Path(folds_path).read_text(encoding='utf-8'))
    return len(cfg['walk_forward']['folds'])


def _checkpoint_inventory(checkpoint_root: Path, trial_id: str, lineage: dict[str, Any]) -> list[dict[str, Any]]:
    records=[]
    for fold_id in range(EXPECTED_FOLDS_PER_TRIAL):
        mp=checkpoint_root/trial_id/f'fold-{fold_id:02d}'/'manifest.json'
        payload=load_committed_fold(
            mp,
            expected_trial_id=trial_id,
            expected_fold_id=fold_id,
            expected_lineage=lineage,
        )
        manifest=json.loads(mp.read_text(encoding='utf-8'))
        if int(payload.get('fold_id', -1)) != fold_id:
            raise ValueError('fold payload identity mismatch')
        records.append({
            'trial_id':trial_id,
            'fold_id':fold_id,
            'manifest_sha256':sha256_file(mp),
            'payload_sha256':manifest['payload_sha256'],
        })
    return records


def execute_trial_checkpointed(
    *,
    panel,
    registry,
    folds_path,
    index: int,
    checkpoint_root: str | Path,
    lineage: dict[str, Any],
    stop_after_fold: int,
) -> dict[str, Any]:
    """Execute/resume the real Ridge path through one durable fold boundary.

    The same ``walk_forward_predictions`` loop is used. Earlier folds are loaded
    only if their COMMITTED checkpoint, lineage, payload digest and RNG chain all
    verify. The final call (fold 11) produces the ordinary trial outputs.
    """
    trial=trial_at(registry,index)
    tid=trial['trial_id']; p=trial['params']; seed=int(trial['seed'])
    total_folds=_fold_count(folds_path)
    if total_folds != EXPECTED_FOLDS_PER_TRIAL:
        raise ValueError(f'expected {EXPECTED_FOLDS_PER_TRIAL} frozen folds, got {total_folds}')
    if int(lineage.get('seed', -1)) != seed:
        raise ValueError('checkpoint lineage seed mismatch')
    if int(lineage.get('max_training_rows_per_fold', -1)) != MAX_TRAINING_ROWS_PER_FOLD:
        raise ValueError('checkpoint lineage max_training_rows_per_fold mismatch')
    if lineage.get('runtime_fingerprint_sha256') != runtime_fingerprint_sha256():
        raise ValueError('checkpoint runtime fingerprint mismatch')
    if lineage.get('holdout_opened') or lineage.get('holdout_evaluated'):
        raise ValueError('holdout must remain closed')

    predictions=walk_forward_predictions(
        panel,
        folds_path,
        family='ridge',
        params=p,
        seed=seed,
        max_training_rows_per_fold=MAX_TRAINING_ROWS_PER_FOLD,
        checkpoint_root=checkpoint_root,
        checkpoint_trial_id=tid,
        checkpoint_lineage=lineage,
        stop_after_fold=stop_after_fold,
    )
    if stop_after_fold < total_folds - 1:
        return {
            'index':index,
            'trial_id':tid,
            'seed':seed,
            'checkpoint_only':True,
            'committed_through_fold':stop_after_fold,
            'training_rows':predictions.training_rows,
            'prediction_rows':predictions.prediction_rows,
        }

    oos=_oos_index(panel,folds_path)
    weights=prediction_to_weights(panel,predictions,cost_gate_bps=float(p['cost_gate_bps']))
    base=_run(panel,weights,1.0).reindex(oos).fillna(0.0)
    stressed=_run(panel,weights,2.0).reindex(oos).fillna(0.0)
    severe=_run(panel,weights,3.0).reindex(oos).fillna(0.0)
    inventory=_checkpoint_inventory(Path(checkpoint_root),tid,lineage)
    return {
        'index':index,
        'trial_id':tid,
        'seed':seed,
        'failure':None,
        'fold_inventory':inventory,
        'base':pd.DataFrame({tid:base},index=oos),
        'stressed':pd.DataFrame({tid:stressed},index=oos),
        'severe':pd.DataFrame({tid:severe},index=oos),
    }


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_trial(result: dict[str, Any], root: Path, lineage: dict[str, Any]) -> None:
    if result.get('checkpoint_only'):
        raise ValueError('partial fold checkpoint cannot be written as a completed Ridge trial')
    root.mkdir(parents=True, exist_ok=True)
    for key in ('base', 'stressed', 'severe'):
        result[key].to_csv(root / f'{key}.csv')
    fold_inventory=result.get('fold_inventory') or []
    manifest = {
        'schema_version':'2.2.0',
        'stage':'RIDGE_SINGLE_TRIAL',
        'execution_status':'COMPLETED',
        'index':result['index'],
        'trial_id':result['trial_id'],
        'seed':result['seed'],
        'failure':result['failure'],
        'fold_checkpoint_count':len(fold_inventory),
        'fold_inventory':fold_inventory,
        'holdout_opened':False,
        'holdout_evaluated':False,
        **lineage,
    }
    manifest.update({f'{k}_sha256': _sha(root / f'{k}.csv') for k in ('base','stressed','severe')})
    (root/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    (root/'result.sha256').write_text(_sha(root/'manifest.json')+'  manifest.json\n',encoding='utf-8')


def load_trial(root: Path) -> dict[str, Any]:
    mp=root/'manifest.json'; m=json.loads(mp.read_text())
    if m.get('stage')!='RIDGE_SINGLE_TRIAL' or m.get('execution_status')!='COMPLETED':
        raise ValueError('ridge result is not a completed single-trial artifact')
    if _sha(mp)!=(root/'result.sha256').read_text().split()[0]:
        raise ValueError('tampered ridge trial manifest')
    frames={}
    for key in ('base','stressed','severe'):
        p=root/f'{key}.csv'
        if _sha(p)!=m[f'{key}_sha256']:
            raise ValueError(f'tampered ridge trial {key}')
        frames[key]=pd.read_csv(p,index_col=0,parse_dates=True)
    return {'manifest':m,**frames}


def _valid_sha256(value: Any) -> bool:
    return isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value.lower())


def validate_trials(registry: dict[str, Any], results: list[dict[str, Any]]) -> tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame,list[dict[str,Any]]]:
    if len(results)!=RIDGE_TRIAL_COUNT:
        raise ValueError('exactly 27 ridge trial artifacts required')
    expected=ridge_trials(registry); ids=[t['trial_id'] for t in expected]; by_id={}
    lineage=(
        'parent_checkpoint_sha256','dataset_sha256','registry_sha256','folds_sha256',
        'config_sha256','source_commit_sha','runtime_fingerprint_sha256',
    )
    fold_records=[]
    for r in results:
        m=r['manifest']; tid=m.get('trial_id')
        if m.get('execution_status')!='COMPLETED':
            raise ValueError('incomplete ridge trial artifact')
        if tid in by_id:
            raise ValueError('duplicate ridge trial artifact')
        if tid not in ids:
            raise ValueError('unknown ridge trial id')
        if m.get('holdout_opened') or m.get('holdout_evaluated'):
            raise ValueError('holdout governance violation')
        inventory=m.get('fold_inventory') or []
        if int(m.get('fold_checkpoint_count', -1)) != EXPECTED_FOLDS_PER_TRIAL or len(inventory) != EXPECTED_FOLDS_PER_TRIAL:
            raise ValueError('ridge trial lacks exact 12-fold checkpoint evidence')
        for entry in inventory:
            if entry.get('trial_id') != tid:
                raise ValueError('fold checkpoint trial identity mismatch')
            if not _valid_sha256(entry.get('manifest_sha256')) or not _valid_sha256(entry.get('payload_sha256')):
                raise ValueError('invalid fold checkpoint digest')
            fold_records.append({'trial_id':tid,'fold_id':int(entry['fold_id'])})
        by_id[tid]=r
    if set(by_id)!=set(ids):
        raise ValueError('ridge 27/27 exactly-once violation')
    validate_fold_inventory(fold_records,ids)
    for key in lineage:
        values={r['manifest'].get(key) for r in results}
        if len(values)!=1 or next(iter(values)) in (None,''):
            raise ValueError(f'lineage mismatch: {key}')
    for i,t in enumerate(expected):
        m=by_id[t['trial_id']]['manifest']
        if m.get('index')!=i or int(m.get('seed'))!=int(t['seed']):
            raise ValueError('ridge preregistration identity mismatch')
    frames=[]
    for key in ('base','stressed','severe'):
        frame=pd.concat([by_id[tid][key] for tid in ids],axis=1)
        if list(frame.columns)!=ids:
            raise ValueError('deterministic ridge column order mismatch')
        frames.append(frame)
    failures=[by_id[tid]['manifest']['failure'] for tid in ids if by_id[tid]['manifest'].get('failure')]
    return frames[0],frames[1],frames[2],failures


def reduce_and_adjudicate(*,panel,registry,folds_path,structural_base,structural_stressed,structural_severe,results):
    base,stressed,severe,failures=validate_trials(registry,results)
    return adjudicate_ridge_outputs(
        panel=panel,folds_path=folds_path,structural_base=structural_base,
        structural_stressed=structural_stressed,structural_severe=structural_severe,
        ridge_base=base,ridge_stressed=stressed,ridge_severe=severe,ridge_failures=failures,
    )
