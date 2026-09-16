from pathlib import Path
import json
import pytest

from ar_tf.ridge_fold_resume import (
    EXPECTED_FOLDS,
    commit_fold_checkpoint,
    load_committed_fold,
    validate_fold_inventory,
)


def lineage():
    return {
        "cp02_artifact_id": 10419024917,
        "cp02_digest": "sha256:974d02bbce33d7809c6cc3f44a21f3d2e249ec320d7362e18fedd584e20e25ce",
        "dataset_sha256": "dataset",
        "registry_sha256": "registry",
        "folds_sha256": "folds",
        "scientific_config_sha256": "config",
        "seed": 7,
        "holdout_opened": False,
        "holdout_evaluated": False,
    }


def test_transactional_checkpoint_round_trip(tmp_path):
    mp = commit_fold_checkpoint(tmp_path, trial_id="ridge-00", fold_id=0, lineage=lineage(), payload={"prediction": [1.0], "status": "OK"})
    got = load_committed_fold(mp, expected_trial_id="ridge-00", expected_fold_id=0, expected_lineage=lineage())
    assert got == {"prediction": [1.0], "status": "OK"}


def test_tampered_payload_is_rejected(tmp_path):
    mp = commit_fold_checkpoint(tmp_path, trial_id="ridge-00", fold_id=0, lineage=lineage(), payload={"x": 1})
    (mp.parent / "payload.json").write_text('{"x":2}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="digest"):
        load_committed_fold(mp, expected_trial_id="ridge-00", expected_fold_id=0, expected_lineage=lineage())


def test_started_or_truncated_manifest_is_rejected(tmp_path):
    mp = commit_fold_checkpoint(tmp_path, trial_id="ridge-00", fold_id=0, lineage=lineage(), payload={"x": 1})
    m = json.loads(mp.read_text())
    m["state"] = "STARTED"
    mp.write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(ValueError, match="COMMITTED"):
        load_committed_fold(mp, expected_trial_id="ridge-00", expected_fold_id=0, expected_lineage=lineage())


def test_lineage_mismatch_and_holdout_are_rejected(tmp_path):
    mp = commit_fold_checkpoint(tmp_path, trial_id="ridge-00", fold_id=0, lineage=lineage(), payload={"x": 1})
    bad = lineage(); bad["dataset_sha256"] = "other"
    with pytest.raises(ValueError, match="lineage"):
        load_committed_fold(mp, expected_trial_id="ridge-00", expected_fold_id=0, expected_lineage=bad)
    bad_holdout = lineage(); bad_holdout["holdout_evaluated"] = True
    with pytest.raises(ValueError, match="holdout"):
        commit_fold_checkpoint(tmp_path, trial_id="ridge-00", fold_id=1, lineage=bad_holdout, payload={"x": 1})


def test_inventory_requires_exact_324_unique_folds():
    tids = [f"ridge-{i:02d}" for i in range(27)]
    records = [{"trial_id": tid, "fold_id": fid} for tid in tids for fid in range(12)]
    result = validate_fold_inventory(records, tids)
    assert result["verified_folds"] == EXPECTED_FOLDS == 324
    assert result["verified_trials"] == 27
    with pytest.raises(ValueError, match="duplicate"):
        validate_fold_inventory(records + [records[0]], tids)
    with pytest.raises(ValueError, match="invalid fold inventory"):
        validate_fold_inventory(records[:-1], tids)


def test_resume_equivalence_property(tmp_path):
    """Committed folds reused after an interruption are byte-for-byte equivalent."""
    lin = lineage()
    uninterrupted = {}
    for fid in range(12):
        payload = {"fold": fid, "prediction": [fid / 10.0], "weights": [fid / 20.0], "base": fid, "stressed": fid - 1, "severe": fid - 2}
        uninterrupted[fid] = payload
        commit_fold_checkpoint(tmp_path / "run", trial_id="ridge-00", fold_id=fid, lineage=lin, payload=payload)
    for interruption in (1, 6, 11):
        resumed = {}
        for fid in range(12):
            mp = tmp_path / "run" / "ridge-00" / f"fold-{fid:02d}" / "manifest.json"
            if fid <= interruption:
                resumed[fid] = load_committed_fold(mp, expected_trial_id="ridge-00", expected_fold_id=fid, expected_lineage=lin)
            else:
                payload = uninterrupted[fid]
                commit_fold_checkpoint(tmp_path / f"resume-{interruption}", trial_id="ridge-00", fold_id=fid, lineage=lin, payload=payload)
                rmp = tmp_path / f"resume-{interruption}" / "ridge-00" / f"fold-{fid:02d}" / "manifest.json"
                resumed[fid] = load_committed_fold(rmp, expected_trial_id="ridge-00", expected_fold_id=fid, expected_lineage=lin)
        assert resumed == uninterrupted


def test_real_walk_forward_resume_matches_monolith_predictions_weights_and_cost_paths(tmp_path):
    import numpy as np
    import pandas as pd
    import yaml

    from ar_tf.classical_tournament import _run
    from ar_tf.ml_trials import prediction_to_weights, walk_forward_predictions
    from ar_tf.research_panel import ResearchPanel

    idx=pd.date_range('2025-01-01',periods=260,freq='D',tz='UTC')
    cols=[f'A{i}' for i in range(6)]
    t=np.arange(len(idx),dtype=float)
    close=pd.DataFrame(index=idx,columns=cols,dtype=float)
    for j,c in enumerate(cols):
        close[c]=100.0*np.exp((0.0008+0.00008*j)*t + 0.015*np.sin(t/(9.0+j)))
    qv=pd.DataFrame({c:25_000_000.0 + (j+1)*100_000.0 + 10_000.0*np.cos(t/7.0) for j,c in enumerate(cols)},index=idx)
    tc=pd.DataFrame(1000.0,index=idx,columns=cols)
    panel=ResearchPanel(close=close,high=close*1.01,low=close*0.99,quote_volume=qv,trade_count=tc,
        research_end=idx[-2],holdout_start=idx[-1]+pd.Timedelta(days=1))
    folds={'walk_forward':{'folds':[
        {'train_start':'2025-01-01','train_end':'2025-05-21','test_start':'2025-05-23','test_end':'2025-06-15'},
        {'train_start':'2025-01-01','train_end':'2025-06-20','test_start':'2025-06-22','test_end':'2025-07-15'},
        {'train_start':'2025-01-01','train_end':'2025-07-20','test_start':'2025-07-22','test_end':'2025-08-14'},
    ]}}
    folds_path=tmp_path/'folds.yaml'; folds_path.write_text(yaml.safe_dump(folds),encoding='utf-8')
    params={'alpha':1.0,'horizon_days':7,'cost_gate_bps':10}
    mono=walk_forward_predictions(panel,folds_path,family='ridge',params=params,seed=7,max_training_rows_per_fold=120)

    lin={'parent_checkpoint_sha256':'a'*64,'dataset_sha256':'b'*64,'registry_sha256':'c'*64,'folds_sha256':'d'*64,
        'config_sha256':'e'*64,'source_commit_sha':'1'*40,'runtime_fingerprint_sha256':'f'*64,'seed':7,
        'max_training_rows_per_fold':120,'holdout_opened':False,'holdout_evaluated':False}
    root=tmp_path/'checkpoints'
    walk_forward_predictions(panel,folds_path,family='ridge',params=params,seed=7,max_training_rows_per_fold=120,
        checkpoint_root=root,checkpoint_trial_id='ridge-fixture',checkpoint_lineage=lin,stop_after_fold=0)
    walk_forward_predictions(panel,folds_path,family='ridge',params=params,seed=7,max_training_rows_per_fold=120,
        checkpoint_root=root,checkpoint_trial_id='ridge-fixture',checkpoint_lineage=lin,stop_after_fold=1)
    resumed=walk_forward_predictions(panel,folds_path,family='ridge',params=params,seed=7,max_training_rows_per_fold=120,
        checkpoint_root=root,checkpoint_trial_id='ridge-fixture',checkpoint_lineage=lin,stop_after_fold=2)

    pd.testing.assert_frame_equal(mono.forecast,resumed.forecast,check_exact=True)
    pd.testing.assert_frame_equal(mono.uncertainty,resumed.uncertainty,check_exact=True)
    assert mono.training_rows==resumed.training_rows
    assert mono.prediction_rows==resumed.prediction_rows
    mono_w=prediction_to_weights(panel,mono,cost_gate_bps=10)
    resumed_w=prediction_to_weights(panel,resumed,cost_gate_bps=10)
    pd.testing.assert_frame_equal(mono_w,resumed_w,check_exact=True)
    for multiplier in (1.0,2.0,3.0):
        pd.testing.assert_series_equal(_run(panel,mono_w,multiplier),_run(panel,resumed_w,multiplier),check_exact=True)


def test_real_resume_fails_closed_on_rng_checkpoint_tamper(tmp_path):
    import numpy as np
    import pandas as pd
    import yaml

    from ar_tf.ml_trials import walk_forward_predictions
    from ar_tf.research_panel import ResearchPanel

    idx=pd.date_range('2025-01-01',periods=180,freq='D',tz='UTC'); cols=['A','B','C']
    t=np.arange(len(idx),dtype=float)
    close=pd.DataFrame({c:100.0*np.exp((0.001+0.0001*j)*t) for j,c in enumerate(cols)},index=idx)
    panel=ResearchPanel(close=close,high=close*1.01,low=close*0.99,
        quote_volume=pd.DataFrame(30_000_000.0,index=idx,columns=cols),
        trade_count=pd.DataFrame(1000.0,index=idx,columns=cols),research_end=idx[-2],holdout_start=idx[-1]+pd.Timedelta(days=1))
    folds={'walk_forward':{'folds':[{'train_start':'2025-01-01','train_end':'2025-05-10','test_start':'2025-05-12','test_end':'2025-05-25'}]}}
    fp=tmp_path/'folds.yaml'; fp.write_text(yaml.safe_dump(folds),encoding='utf-8')
    params={'alpha':1.0,'horizon_days':1,'cost_gate_bps':10}
    lin={'seed':7,'max_training_rows_per_fold':80,'holdout_opened':False,'holdout_evaluated':False}
    root=tmp_path/'cp'
    walk_forward_predictions(panel,fp,family='ridge',params=params,seed=7,max_training_rows_per_fold=80,
        checkpoint_root=root,checkpoint_trial_id='ridge-x',checkpoint_lineage=lin,stop_after_fold=0)
    mp=root/'ridge-x'/'fold-00'/'manifest.json'; payload=mp.parent/'payload.json'
    data=json.loads(payload.read_text()); data['rng_state_before']['state']['state']+=1
    payload.write_text(json.dumps(data,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    with pytest.raises(ValueError,match='digest'):
        walk_forward_predictions(panel,fp,family='ridge',params=params,seed=7,max_training_rows_per_fold=80,
            checkpoint_root=root,checkpoint_trial_id='ridge-x',checkpoint_lineage=lin,stop_after_fold=0)
