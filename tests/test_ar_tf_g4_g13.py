import json
from pathlib import Path

import pandas as pd

from ar_tf.bias_audit import audit_frozen_dataset
from ar_tf.g4_g13_contract import evaluate_g4_g13
from ar_tf.preregistration import build_preregistration


def _write_minimal_dataset(root: Path):
    (root / 'market').mkdir(parents=True)
    cert = {
        'decision':'FROZEN_DATASET','frozen':True,'unresolved_count':0,'unresolved_gap_count':0,
        'unresolved_anomaly_count':0,'invalid_checksum_evidence_count':0,
        'lifecycle_binding_verified':True,'source_plan_binding_verified':True,'holdout_evaluated':False,
        'market_episode_count':1,'dataset_sha256':'a'*64,'verified_lifecycle_sha256':'b'*64,
    }
    (root/'dataset-freeze-certificate.json').write_text(json.dumps(cert))
    pd.DataFrame({
        'timestamp':['2025-07-30 00:00:00+00:00','2025-07-31 00:00:00+00:00','2025-08-01 00:00:00+00:00'],
        'symbol':['BTCUSDT']*3,'episode_id':[1]*3,
        'open':[100,101,102],'high':[102,103,104],'low':[99,100,101],'close':[101,102,103],
        'volume':[10,11,12],'quote_volume':[1000,1100,1200],'trade_count':[100,110,120],
    }).to_csv(root/'market'/'BTCUSDT__E01.csv',index=False)


def _write_folds(path: Path):
    path.write_text("""version: 1
holdout:
  start: '2025-08-01T00:00:00Z'
  opened: false
research_window:
  end: '2025-07-31T23:59:59Z'
""")


def test_g4_audit_sees_holdout_boundaries_but_never_evaluates_holdout_values(tmp_path):
    ds=tmp_path/'ds'; _write_minimal_dataset(ds)
    folds=tmp_path/'folds.yaml'; _write_folds(folds)
    r=audit_frozen_dataset(ds,folds)
    assert r['decision']=='PASS'
    assert r['holdout_rows_seen_structurally']==1
    assert r['holdout_values_evaluated'] is False
    assert r['holdout_opened'] is False


def test_g5_preregistration_is_exactly_407_and_bound_to_all_identities():
    b=build_preregistration(
        dataset_binding_path='config/ar_tf_frozen_dataset_binding_2026.json',
        registry_spec_path='config/ar_tf_trial_registry_v1.yaml',
        strategy_config_path='config/ar_tf_master_strategy_tournament_2026.yaml',
        folds_path='config/ar_tf_oos_folds_2026.yaml',
        source_commit_sha='c'*40,
    )
    m=b['manifest']; r=b['registry']
    assert m['trial_count']==407
    assert r['trial_count']==407
    assert all(t['source_commit_sha']=='c'*40 for t in r['trials'])
    assert all(t['strategy_config_sha256']==m['strategy_config_sha256'] for t in r['trials'])
    assert all(t['fold_definition_sha256']==m['fold_definition_sha256'] for t in r['trials'])
    assert r['holdout_evaluated'] is False


def test_g4_g13_contract_does_not_promote_missing_tournament_evidence():
    g4={'decision':'PASS','holdout_values_evaluated':False,'holdout_opened':False}
    g5={
        'decision':'PASS','state':'PREREGISTERED_NOT_EXECUTED','trial_count':407,'holdout_evaluated':False,
        'source_commit_sha':'c'*40,'dataset_sha256':'a'*64,'lifecycle_sha256':'b'*64,
        'strategy_config_sha256':'d'*64,'fold_definition_sha256':'e'*64,'trial_registry_sha256':'f'*64,
    }
    c=evaluate_g4_g13(bias_audit=g4,preregistration=g5,tournament=None)
    assert c['gates']['G4']['status']=='PASS'
    assert c['gates']['G5']['status']=='PASS'
    assert all(c['gates'][x]['status']=='BLOCKED' for x in ('G6','G7','G8','G9','G10','G11','G12','G13'))
    assert c['decision']=='NO_EDGE_VERIFIED'
    assert c['holdout_opened'] is False
