from __future__ import annotations
import hashlib,json,os,platform
from pathlib import Path
import numpy as np,pandas as pd
from ar_tf.ml_trials import _feature_panels,_folds,_future_return
from ar_tf.research_panel import load_research_panel
from ar_tf.ridge_resume import trial_at

root=Path("artifacts/g4_g13"); folds_path=Path("config/ar_tf_oos_folds_2026.yaml")
registry_path=root/"preregistration/preregistered-trial-registry.json"; binding_path=Path("config/ar_tf_frozen_dataset_binding_2026.json")
registry=json.loads(registry_path.read_text()); binding=json.loads(binding_path.read_text()); trial=trial_at(registry,int(os.environ["TRIAL_INDEX"]))
panel=load_research_panel(root/"frozen_dataset",folds_path); params=trial["params"]; horizon=int(params["horizon_days"]); fold=_folds(folds_path)[int(os.environ["FOLD_ID"])]
features=_feature_panels(panel); target=_future_return(panel,horizon)
train_start=pd.Timestamp(fold["train_start"],tz="UTC"); train_end=pd.Timestamp(fold["train_end"],tz="UTC")-pd.Timedelta(days=horizon)
test_start=pd.Timestamp(fold["test_start"],tz="UTC"); test_end=pd.Timestamp(fold["test_end"],tz="UTC")
train_dates=panel.close.index[(panel.close.index>=train_start)&(panel.close.index<=train_end)]; test_dates=panel.close.index[(panel.close.index>=test_start)&(panel.close.index<=test_end)]
n_features=len(features); n_markets=len(panel.close.columns); cap=100_000
# Bounds are computed before long-frame/NumPy/scaler materialization. They are not claims about post-dropna exact rows.
train_candidate=len(train_dates)*n_markets; test_candidate=len(test_dates)*n_markets; train_capped=min(train_candidate,cap); itemsize=np.dtype(float).itemsize
objects={
 "train":{"rows_upper_bound":train_candidate,"columns":n_features+1,"expected_dense_bytes_upper_bound":train_candidate*(n_features+1)*itemsize},
 "X":{"rows_upper_bound":train_capped,"columns":n_features,"dtype":str(np.dtype(float)),"expected_bytes_upper_bound":train_capped*n_features*itemsize},
 "Xtest":{"rows_upper_bound":test_candidate,"columns":n_features,"dtype":str(np.dtype(float)),"expected_bytes_upper_bound":test_candidate*n_features*itemsize},
 "Xs":{"rows_upper_bound":train_capped,"columns":n_features,"dtype":str(np.dtype(float)),"expected_bytes_upper_bound":train_capped*n_features*itemsize},
 "Xts":{"rows_upper_bound":test_candidate,"columns":n_features,"dtype":str(np.dtype(float)),"expected_bytes_upper_bound":test_candidate*n_features*itemsize}}
sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
out={"schema_version":"1.0.0","diagnostic_only":True,"scientific_sha":os.environ["SCIENTIFIC_SHA"],"trial_id":trial["trial_id"],"fold_id":int(os.environ["FOLD_ID"]),"dataset_sha256":binding["dataset_sha256"],"registry_sha256":sha(registry_path),"folds_sha256":sha(folds_path),"scientific_config_sha256":sha(binding_path),"max_training_rows_per_fold":cap,"feature_count":n_features,"market_count":n_markets,"float_itemsize":itemsize,"objects":objects,"note":"Pre-materialization upper bounds only; exact post-dropna shapes require materialization and are intentionally not inferred.","runtime":{"python":platform.python_version(),"platform":platform.platform()}}
Path("diagnostics").mkdir(exist_ok=True); Path("diagnostics/fold06-preflight.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
print(json.dumps(out,indent=2,sort_keys=True))
