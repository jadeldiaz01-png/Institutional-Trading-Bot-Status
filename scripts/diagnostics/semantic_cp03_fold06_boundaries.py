#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import runpy
import sys
import time
from pathlib import Path

import pandas as pd
from sklearn.preprocessing import StandardScaler


def rss_kb() -> int:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1])
    return -1


def mark(stage: str, obj=None) -> None:
    payload = {
        "stage": stage,
        "monotonic_ns": time.monotonic_ns(),
        "rss_kb": rss_kb(),
    }
    if obj is not None:
        shape = getattr(obj, "shape", None)
        dtype = getattr(obj, "dtype", None)
        payload["shape"] = list(shape) if shape is not None else None
        payload["dtype"] = str(dtype) if dtype is not None else None
    print("SEMANTIC_BOUNDARY " + json.dumps(payload, separators=(",", ":")), flush=True)


def main() -> None:
    science = Path(os.environ["SCIENCE_ROOT"]).resolve()
    os.chdir(science)
    sys.path.insert(0, str(science / "src"))
    import ar_tf.ml_trials as ml

    original_training = ml._long_training_frame
    original_reindex = pd.DataFrame.reindex
    original_stack = pd.DataFrame.stack
    original_join = pd.DataFrame.join
    original_replace = pd.DataFrame.replace
    original_dropna = pd.DataFrame.dropna
    original_features = ml._long_features
    original_to_numpy = pd.DataFrame.to_numpy
    original_fit = StandardScaler.fit
    original_transform = StandardScaler.transform

    state = {
        "long_features_calls": 0,
        "to_numpy_calls": 0,
        "transform_calls": 0,
        "inside_training": False,
        "target_reindexed": False,
        "target_stacked": False,
        "train_joined": False,
        "train_replaced": False,
        "train_dropped": False,
    }

    def training(features, target, dates):
        mark("train.before")
        state["inside_training"] = True
        try:
            out = original_training(features, target, dates)
        finally:
            state["inside_training"] = False
        mark("train.after", out)
        return out

    def reindex(self, *args, **kwargs):
        trace = state["inside_training"] and not state["target_reindexed"]
        if trace:
            mark("train.target.reindex.before", self)
        out = original_reindex(self, *args, **kwargs)
        if trace:
            state["target_reindexed"] = True
            mark("train.target.reindex.after", out)
        return out

    def stack(self, *args, **kwargs):
        trace = state["inside_training"] and state["target_reindexed"] and not state["target_stacked"]
        if trace:
            mark("train.target.stack.before", self)
        out = original_stack(self, *args, **kwargs)
        if trace:
            state["target_stacked"] = True
            mark("train.target.stack.after", out)
        return out

    def join(self, other, *args, **kwargs):
        trace = state["inside_training"] and state["target_stacked"] and not state["train_joined"]
        if trace:
            mark("train.join.before", self)
        out = original_join(self, other, *args, **kwargs)
        if trace:
            state["train_joined"] = True
            mark("train.join.after", out)
        return out

    def replace(self, *args, **kwargs):
        trace = state["inside_training"] and state["train_joined"] and not state["train_replaced"]
        if trace:
            mark("train.replace.before", self)
        out = original_replace(self, *args, **kwargs)
        if trace:
            state["train_replaced"] = True
            mark("train.replace.after", out)
        return out

    def dropna(self, *args, **kwargs):
        trace = state["inside_training"] and state["train_replaced"] and not state["train_dropped"]
        if trace:
            mark("train.dropna.before", self)
        out = original_dropna(self, *args, **kwargs)
        if trace:
            state["train_dropped"] = True
            mark("train.dropna.after", out)
        return out

    def long_features(features, dates):
        state["long_features_calls"] += 1
        # The first call is nested inside train construction; the second is Xtest source.
        label = "train.features" if state["long_features_calls"] % 2 else "test"
        mark(label + ".before")
        out = original_features(features, dates)
        mark(label + ".after", out)
        return out

    def to_numpy(self, *args, **kwargs):
        state["to_numpy_calls"] += 1
        label = {1: "X", 2: "Xtest"}.get(state["to_numpy_calls"], "to_numpy")
        mark(label + ".before", self)
        out = original_to_numpy(self, *args, **kwargs)
        mark(label + ".after", out)
        return out

    def scaler_fit(self, X, *args, **kwargs):
        mark("scaler.fit.before", X)
        out = original_fit(self, X, *args, **kwargs)
        mark("scaler.fit.after")
        return out

    def scaler_transform(self, X, *args, **kwargs):
        state["transform_calls"] += 1
        label = "Xs" if state["transform_calls"] == 1 else "Xts"
        mark(label + ".before", X)
        out = original_transform(self, X, *args, **kwargs)
        mark(label + ".after", out)
        return out

    ml._long_training_frame = training
    ml._long_features = long_features
    pd.DataFrame.reindex = reindex
    pd.DataFrame.stack = stack
    pd.DataFrame.join = join
    pd.DataFrame.replace = replace
    pd.DataFrame.dropna = dropna
    pd.DataFrame.to_numpy = to_numpy
    StandardScaler.fit = scaler_fit
    StandardScaler.transform = scaler_transform

    mark("driver.start")
    runpy.run_path(str(science / "scripts/ar_tf_ridge_fold_step.py"), run_name="__main__")


if __name__ == "__main__":
    main()
