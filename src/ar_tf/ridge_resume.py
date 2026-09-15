from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .classical_tournament import _oos_index, _run
from .ml_trials import prediction_to_weights, walk_forward_predictions

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


def execute_trial(*, panel, registry, folds_path, index: int) -> dict[str, Any]:
    trial = trial_at(registry, index)
    oos = _oos_index(panel, folds_path)
    p = trial['params']
    predictions = walk_forward_predictions(
        panel, folds_path, family='ridge', params=p, seed=int(trial['seed']),
        max_training_rows_per_fold=100_000,
    )
    weights = prediction_to_weights(panel, predictions, cost_gate_bps=float(p['cost_gate_bps']))
    tid = trial['trial_id']
    return {
        'index': index,
        'trial_id': tid,
        'seed': int(trial['seed']),
        'base': pd.DataFrame({tid: _run(panel, weights, 1.0).reindex(oos).fillna(0.0)}, index=oos),
        'stressed': pd.DataFrame({tid: _run(panel, weights, 2.0).reindex(oos).fillna(0.0)}, index=oos),
        'severe': pd.DataFrame({tid: _run(panel, weights, 3.0).reindex(oos).fillna(0.0)}, index=oos),
    }


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_trial(result: dict[str, Any], root: Path, lineage: dict[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for key in ('base', 'stressed', 'severe'):
        result[key].to_csv(root / f'{key}.csv')
    manifest = {
        'schema_version': '2.0.0',
        'stage': 'RIDGE_SINGLE_TRIAL',
        'execution_status': 'COMPLETED',
        'index': result['index'],
        'trial_id': result['trial_id'],
        'seed': result['seed'],
        'holdout_opened': False,
        'holdout_evaluated': False,
        **lineage,
    }
    manifest.update({f'{k}_sha256': _sha(root / f'{k}.csv') for k in ('base', 'stressed', 'severe')})
    (root / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
    (root / 'result.sha256').write_text(_sha(root / 'manifest.json') + '  manifest.json\n')


def load_trial(root: Path) -> dict[str, Any]:
    manifest_path = root / 'manifest.json'
    m = json.loads(manifest_path.read_text())
    if m.get('stage') != 'RIDGE_SINGLE_TRIAL' or m.get('execution_status') != 'COMPLETED':
        raise ValueError('ridge result is not a completed single-trial artifact')
    expected_manifest = (root / 'result.sha256').read_text().split()[0]
    if _sha(manifest_path) != expected_manifest:
        raise ValueError('tampered ridge trial manifest')
    frames = {}
    for key in ('base', 'stressed', 'severe'):
        p = root / f'{key}.csv'
        if _sha(p) != m[f'{key}_sha256']:
            raise ValueError(f'tampered ridge trial {key}')
        frames[key] = pd.read_csv(p, index_col=0, parse_dates=True)
    return {'manifest': m, **frames}


def validate_trials(registry: dict[str, Any], results: list[dict[str, Any]]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if len(results) != RIDGE_TRIAL_COUNT:
        raise ValueError('exactly 27 ridge trial artifacts required')
    expected_trials = ridge_trials(registry)
    expected_ids = [t['trial_id'] for t in expected_trials]
    by_id: dict[str, dict[str, Any]] = {}
    lineage = ('parent_checkpoint_sha256', 'dataset_sha256', 'registry_sha256', 'folds_sha256', 'config_sha256')
    for result in results:
        m = result['manifest']
        tid = m.get('trial_id')
        if tid in by_id:
            raise ValueError('duplicate ridge trial artifact')
        if tid not in expected_ids:
            raise ValueError('unknown ridge trial id')
        if m.get('holdout_opened') or m.get('holdout_evaluated'):
            raise ValueError('holdout governance violation')
        by_id[tid] = result
    if set(by_id) != set(expected_ids):
        raise ValueError('ridge 27/27 exactly-once violation')
    for key in lineage:
        if len({r['manifest'].get(key) for r in results}) != 1 or next(iter({r['manifest'].get(key) for r in results})) in (None, ''):
            raise ValueError(f'lineage mismatch: {key}')
    for index, trial in enumerate(expected_trials):
        m = by_id[trial['trial_id']]['manifest']
        if m.get('index') != index or int(m.get('seed')) != int(trial['seed']):
            raise ValueError('ridge preregistration identity mismatch')
    frames = []
    for key in ('base', 'stressed', 'severe'):
        frame = pd.concat([by_id[tid][key] for tid in expected_ids], axis=1)
        if list(frame.columns) != expected_ids:
            raise ValueError('deterministic ridge column order mismatch')
        frames.append(frame)
    return tuple(frames)


def reduce_trials(*, registry: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    base, stressed, severe = validate_trials(registry, results)
    return {
        'schema_version': '2.0.0',
        'stage': 'RIDGE_REDUCER',
        'execution_status': 'COMPLETED',
        'ridge_trial_count': RIDGE_TRIAL_COUNT,
        'trial_count_total': 149,
        'holdout_opened': False,
        'holdout_evaluated': False,
        'paper_authorized': False,
        'testnet_authorized': False,
        'shadow_authorized': False,
        'live_pilot_authorized': False,
        'live_authorized': False,
        'decision': 'RIDGE_27_REDUCED_PENDING_EQUIVALENCE',
        'gradient_boosting_admitted': False,
        'ridge_base': base,
        'ridge_stressed': stressed,
        'ridge_severe': severe,
    }
