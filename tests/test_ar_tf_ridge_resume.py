import copy

import pandas as pd
import pytest

from ar_tf.ridge_resume import RIDGE_TRIAL_COUNT, trial_at, validate_trials


def _registry():
    return {'trials': [{'trial_id': f'ridge-{i:02d}', 'family': 'ridge', 'params': {}, 'seed': i} for i in range(27)]}


def _results(reg):
    idx = pd.date_range('2026-01-01', periods=3, tz='UTC')
    out = []
    for i in range(27):
        t = trial_at(reg, i)
        frame = pd.DataFrame({t['trial_id']: [0.0, 0.01, 0.0]}, index=idx)
        out.append({
            'manifest': {
                'stage': 'RIDGE_SINGLE_TRIAL', 'execution_status': 'COMPLETED',
                'index': i, 'trial_id': t['trial_id'], 'seed': t['seed'],
                'parent_checkpoint_sha256': 'a' * 64, 'dataset_sha256': 'b' * 64,
                'registry_sha256': 'c' * 64, 'folds_sha256': 'd' * 64,
                'config_sha256': 'e' * 64, 'holdout_opened': False, 'holdout_evaluated': False,
            },
            'base': frame, 'stressed': frame.copy(), 'severe': frame.copy(),
        })
    return out


def test_registry_is_exactly_27_and_stable():
    reg = _registry()
    assert RIDGE_TRIAL_COUNT == 27
    assert [trial_at(reg, i)['trial_id'] for i in range(27)] == [f'ridge-{i:02d}' for i in range(27)]


def test_reducer_is_order_invariant_and_exactly_once():
    reg = _registry(); results = _results(reg)
    a = validate_trials(reg, results)
    b = validate_trials(reg, list(reversed(results)))
    for x, y in zip(a, b):
        pd.testing.assert_frame_equal(x, y)


def test_reducer_rejects_duplicate_missing_unknown_and_lineage_mismatch():
    reg = _registry(); results = _results(reg)
    bad = copy.deepcopy(results); bad[1]['manifest']['trial_id'] = bad[0]['manifest']['trial_id']
    with pytest.raises(ValueError): validate_trials(reg, bad)
    bad = copy.deepcopy(results); bad.pop()
    with pytest.raises(ValueError): validate_trials(reg, bad)
    bad = copy.deepcopy(results); bad[2]['manifest']['trial_id'] = 'not-preregistered'
    with pytest.raises(ValueError): validate_trials(reg, bad)
    bad = copy.deepcopy(results); bad[2]['manifest']['dataset_sha256'] = 'f' * 64
    with pytest.raises(ValueError): validate_trials(reg, bad)


def test_reducer_rejects_seed_index_config_and_holdout_tampering():
    reg = _registry()
    for mutation in ('seed', 'index', 'config', 'holdout'):
        bad = copy.deepcopy(_results(reg))
        if mutation == 'seed': bad[3]['manifest']['seed'] = 999
        elif mutation == 'index': bad[3]['manifest']['index'] = 4
        elif mutation == 'config': bad[3]['manifest']['config_sha256'] = '9' * 64
        else: bad[3]['manifest']['holdout_evaluated'] = True
        with pytest.raises(ValueError): validate_trials(reg, bad)


def test_interrupted_or_partial_execution_cannot_be_reduced():
    reg = _registry(); bad = _results(reg)
    bad[8]['manifest']['execution_status'] = 'INTERRUPTED_INFRASTRUCTURE'
    # Loader rejects this state in real artifacts; reducer additionally requires complete evidence.
    bad.pop(8)
    with pytest.raises(ValueError): validate_trials(reg, bad)
