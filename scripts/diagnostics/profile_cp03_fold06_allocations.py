from __future__ import annotations

import os, runpy, sys, time
from pathlib import Path
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

def rss_kb():
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"): return int(line.split()[1])
    return -1

def available_kb():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"): return int(line.split()[1])
    return -1

def describe(obj):
    shape=getattr(obj,"shape",None); dtype=getattr(obj,"dtype",None); nbytes=getattr(obj,"nbytes",None)
    if nbytes is None and hasattr(obj,"memory_usage"):
        try:
            mu=obj.memory_usage(deep=True); nbytes=int(mu.sum() if hasattr(mu,"sum") else mu)
        except Exception: nbytes=None
    return f"type={type(obj).__name__},shape={shape},dtype={dtype},bytes={nbytes}"

def mark(stage,obj=None,started_ns=None):
    elapsed=None if started_ns is None else (time.monotonic_ns()-started_ns)/1_000_000
    suffix="" if obj is None else " "+describe(obj)
    print(f"ALLOC_BOUNDARY stage={stage} rss_kb={rss_kb()} mem_available_kb={available_kb()} elapsed_ms={elapsed}{suffix}",flush=True)

def wrap_method(cls,name,label):
    original=getattr(cls,name)
    def wrapped(self,*args,**kwargs):
        mark(label+".before",self)
        for i,arg in enumerate(args[:2]): mark(f"{label}.arg{i}",arg)
        started=time.monotonic_ns()
        result=original(self,*args,**kwargs)
        mark(label+".after",result,started)
        return result
    setattr(cls,name,wrapped)

def main():
    science=Path(os.environ["SCIENCE_ROOT"]).resolve()
    os.chdir(science); sys.path.insert(0,str(science/"src"))
    import ar_tf.ml_trials as ml

    original_feature_panels=ml._feature_panels
    original_future_return=ml._future_return
    original_long_features=ml._long_features
    original_long_training=ml._long_training_frame

    def feature_panels(panel):
        mark("feature_panels.before"); started=time.monotonic_ns()
        out=original_feature_panels(panel)
        mark("feature_panels.after",next(iter(out.values())),started)
        print("ALLOC_FEATURES "+" ".join(f"{k}={describe(v)}" for k,v in out.items()),flush=True)
        return out

    def future_return(panel,horizon):
        mark("future_return.before"); started=time.monotonic_ns()
        out=original_future_return(panel,horizon); mark("future_return.after",out,started); return out

    def long_features(features,dates):
        print(f"ALLOC_DATES kind=features count={len(dates)}",flush=True)
        mark("long_features.before"); started=time.monotonic_ns()
        out=original_long_features(features,dates); mark("long_features.after",out,started); return out

    def long_training(features,target,dates):
        print(f"ALLOC_DATES kind=training count={len(dates)}",flush=True)
        mark("long_training.before"); started=time.monotonic_ns()
        out=original_long_training(features,target,dates); mark("long_training.after",out,started); return out

    ml._feature_panels=feature_panels; ml._future_return=future_return
    ml._long_features=long_features; ml._long_training_frame=long_training
    wrap_method(pd.DataFrame,"to_numpy","DataFrame.to_numpy")
    wrap_method(StandardScaler,"fit","StandardScaler.fit")
    wrap_method(StandardScaler,"transform","StandardScaler.transform")
    wrap_method(Ridge,"fit","Ridge.fit")
    wrap_method(Ridge,"predict","Ridge.predict")

    mark("driver.start")
    runpy.run_path(str(science/"scripts/ar_tf_ridge_fold_step.py"),run_name="__main__")

if __name__=="__main__": main()
