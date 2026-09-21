from __future__ import annotations
import os, runpy, sys, time
from pathlib import Path

TARGET = Path("src/ar_tf/ml_trials.py").resolve()
WATCH = {131,132,137,154,163,171,172,173,174,187,188,189,190,191,192,193,195,197,207,208,209,211,212,213,223,224,231,238,240,241,242,243,247}

def rss_kb() -> int:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1])
    return -1

def available_kb() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1])
    return -1

def describe(name, obj):
    try:
        shape=getattr(obj,"shape",None); dtype=getattr(obj,"dtype",None)
        nbytes=getattr(obj,"nbytes",None)
        if nbytes is None and hasattr(obj,"memory_usage"):
            mu=obj.memory_usage(deep=True)
            nbytes=int(mu.sum() if hasattr(mu,"sum") else mu)
        return f"{name}:type={type(obj).__name__},shape={shape},dtype={dtype},bytes={nbytes}"
    except Exception as exc:
        return f"{name}:describe_error={type(exc).__name__}"

last = {}
def tracer(frame, event, arg):
    if event != "line" or Path(frame.f_code.co_filename).resolve() != TARGET:
        return tracer
    line=frame.f_lineno
    if line not in WATCH:
        return tracer
    now=time.monotonic_ns()
    rss=rss_kb(); avail=available_kb()
    prev=last.get("rss",rss)
    print(f"ALLOC_TRACE line={line} rss_kb={rss} delta_rss_kb={rss-prev} mem_available_kb={avail} t_ns={now}", flush=True)
    last["rss"]=rss
    loc=frame.f_locals
    for name in ("features","target","train_dates","test_dates","train","test","take","X","y","Xtest","scaler","Xs","Xts","model","pred","train_pred","forecasts","uncertainties","payload"):
        if name in loc:
            print("ALLOC_OBJECT "+describe(name,loc[name]), flush=True)
    return tracer

if __name__ == "__main__":
    science=Path(os.environ["SCIENCE_ROOT"]).resolve()
    os.chdir(science)
    sys.path.insert(0,str(science/"src"))
    sys.settrace(tracer)
    try:
        runpy.run_path(str(science/"scripts/ar_tf_ridge_fold_step.py"),run_name="__main__")
    finally:
        sys.settrace(None)
