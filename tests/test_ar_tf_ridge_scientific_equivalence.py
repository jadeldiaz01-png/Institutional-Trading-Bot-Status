import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from ar_tf.classical_tournament import _run
from ar_tf.ml_trials import (
    FoldCheckpointPause,
    MLPrediction,
    _feature_panels,
    _folds,
    _future_return,
    _long_features,
    _long_training_frame,
    prediction_to_weights,
    walk_forward_predictions,
)
from ar_tf.research_panel import ResearchPanel


def _fixture(tmp_path: Path):
    rng=np.random.default_rng(314159)
    idx=pd.date_range("2020-01-01",periods=420,tz="UTC",freq="D")
    cols=["A","B","C","D"]
    shocks=rng.normal(0.0003,0.02,size=(len(idx),len(cols)))
    close=pd.DataFrame(100*np.exp(np.cumsum(shocks,axis=0)),index=idx,columns=cols)
    volume=pd.DataFrame(rng.lognormal(12,0.5,size=close.shape),index=idx,columns=cols)
    panel=ResearchPanel(
        close=close,high=close*1.01,low=close*0.99,quote_volume=volume,
        trade_count=(volume/1000).round(),research_end=idx[-31],holdout_start=idx[-30],
    )
    folds=[]
    for i in range(12):
        folds.append({
            "train_start":idx[0].date().isoformat(),
            "train_end":idx[239+i*10].date().isoformat(),
            "test_start":idx[240+i*10].date().isoformat(),
            "test_end":idx[249+i*10].date().isoformat(),
        })
    fp=tmp_path/"folds.yml"
    fp.write_text(yaml.safe_dump({"walk_forward":{"folds":folds}}),encoding="utf-8")
    return panel,fp


def _reference(panel,folds_path,params,seed,max_rows):
    horizon=int(params["horizon_days"])
    features=_feature_panels(panel); target=_future_return(panel,horizon)
    forecasts=[]; uncertainties=[]; total_train=0; total_pred=0
    rng=np.random.default_rng(int(seed))
    for fold in _folds(folds_path):
        train_start=pd.Timestamp(fold["train_start"],tz="UTC")
        train_end=pd.Timestamp(fold["train_end"],tz="UTC")
        effective_train_end=train_end-pd.Timedelta(days=horizon)
        test_start=pd.Timestamp(fold["test_start"],tz="UTC")
        test_end=pd.Timestamp(fold["test_end"],tz="UTC")
        train_dates=panel.close.index[(panel.close.index>=train_start)&(panel.close.index<=effective_train_end)]
        test_dates=panel.close.index[(panel.close.index>=test_start)&(panel.close.index<=test_end)]
        train=_long_training_frame(features,target,train_dates)
        test=_long_features(features,test_dates)
        if train.empty or test.empty:
            continue
        if len(train)>max_rows:
            take=np.sort(rng.choice(len(train),size=max_rows,replace=False)); train=train.iloc[take]
        X=train.drop(columns="target").to_numpy(float); y=train["target"].to_numpy(float); Xtest=test.to_numpy(float)
        scaler=StandardScaler().fit(X); Xs=scaler.transform(X); Xts=scaler.transform(Xtest)
        model=Ridge(alpha=float(params["alpha"]),fit_intercept=True); model.fit(Xs,y)
        pred=np.asarray(model.predict(Xts),dtype=float); train_pred=np.asarray(model.predict(Xs),dtype=float)
        residual_scale=float(np.nanstd(y-train_pred,ddof=1)) if len(y)>2 else float("nan")
        forecasts.append(pd.Series(pred,index=test.index)); uncertainties.append(pd.Series(residual_scale,index=test.index))
        total_train+=len(train); total_pred+=len(test)
    f=pd.concat(forecasts).groupby(level=[0,1]).last().unstack("market_id").sort_index()
    u=pd.concat(uncertainties).groupby(level=[0,1]).last().unstack("market_id").sort_index()
    return MLPrediction(f,u,total_train,total_pred)


def _lineage():
    return {
        "parent_checkpoint_sha256":"a"*64,"dataset_sha256":"b"*64,"registry_sha256":"c"*64,
        "folds_sha256":"d"*64,"scientific_config_sha256":"e"*64,
        "holdout_opened":False,"holdout_evaluated":False,
    }


def _assert_prediction_equal(a,b):
    pd.testing.assert_frame_equal(a.forecast,b.forecast,check_exact=True)
    pd.testing.assert_frame_equal(a.uncertainty,b.uncertainty,check_exact=True)
    assert a.training_rows==b.training_rows and a.prediction_rows==b.prediction_rows


def test_monolithic_and_uninterrupted_resumable_are_exact(tmp_path):
    panel,folds=_fixture(tmp_path); params={"alpha":1.0,"horizon_days":1,"cost_gate_bps":5.0}
    ref=_reference(panel,folds,params,7,80)
    got=walk_forward_predictions(panel,folds,family="ridge",params=params,seed=7,max_training_rows_per_fold=80,checkpoint_root=tmp_path/"cp",checkpoint_trial_id="ridge-test",checkpoint_lineage=_lineage())
    _assert_prediction_equal(ref,got)
    wr=prediction_to_weights(panel,ref,cost_gate_bps=5.0); wg=prediction_to_weights(panel,got,cost_gate_bps=5.0)
    pd.testing.assert_frame_equal(wr,wg,check_exact=True)
    for mult in (1.0,2.0,3.0):
        pd.testing.assert_series_equal(_run(panel,wr,mult),_run(panel,wg,mult),check_exact=True)


@pytest.mark.parametrize("kill_fold",[1,6,11])
def test_kill_resume_exact_equivalence(tmp_path,kill_fold):
    panel,folds=_fixture(tmp_path); params={"alpha":1.0,"horizon_days":1,"cost_gate_bps":5.0}
    ref=_reference(panel,folds,params,7,80); root=tmp_path/f"kill-{kill_fold}"
    with pytest.raises(FoldCheckpointPause):
        walk_forward_predictions(panel,folds,family="ridge",params=params,seed=7,max_training_rows_per_fold=80,checkpoint_root=root,checkpoint_trial_id="ridge-test",checkpoint_lineage=_lineage(),pause_after_fold=kill_fold)
    got=walk_forward_predictions(panel,folds,family="ridge",params=params,seed=7,max_training_rows_per_fold=80,checkpoint_root=root,checkpoint_trial_id="ridge-test",checkpoint_lineage=_lineage())
    _assert_prediction_equal(ref,got)


def test_corrupt_committed_fold_fails_closed(tmp_path):
    panel,folds=_fixture(tmp_path); params={"alpha":1.0,"horizon_days":1,"cost_gate_bps":5.0}; root=tmp_path/"corrupt"
    walk_forward_predictions(panel,folds,family="ridge",params=params,seed=7,max_training_rows_per_fold=80,checkpoint_root=root,checkpoint_trial_id="ridge-test",checkpoint_lineage=_lineage())
    payload=root/"ridge-test"/"fold-06"/"payload.json"; obj=json.loads(payload.read_text()); obj["training_rows"]+=1; payload.write_text(json.dumps(obj)+"\n")
    with pytest.raises(ValueError,match="digest"):
        walk_forward_predictions(panel,folds,family="ridge",params=params,seed=7,max_training_rows_per_fold=80,checkpoint_root=root,checkpoint_trial_id="ridge-test",checkpoint_lineage=_lineage())
