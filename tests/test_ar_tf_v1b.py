import json

import numpy as np
import pandas as pd
import pytest

from ar_tf.experiments import JsonlExperimentRegistry, make_record, stable_experiment_id
from ar_tf.ingestion import SymbolLifecycle, active_universe, build_manifest, dataset_digest
from ar_tf.research_runner import freeze_holdout


def frame(start="2020-01-01", n=10):
    idx = pd.date_range(start, periods=n, freq="D", tz="UTC")
    close = pd.Series(np.arange(1, n + 1, dtype=float), index=idx)
    return pd.DataFrame({
        "open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
        "volume": 100.0, "quote_volume": 1000.0, "trade_count": 10,
    }, index=idx)


def test_lifecycle_prevents_survivorship_only_universe():
    lifecycles = {
        "OLDUSDT": SymbolLifecycle("OLDUSDT", pd.Timestamp("2019-01-01", tz="UTC"), pd.Timestamp("2021-01-01", tz="UTC")),
        "NEWUSDT": SymbolLifecycle("NEWUSDT", pd.Timestamp("2022-01-01", tz="UTC")),
    }
    assert active_universe(lifecycles, pd.Timestamp("2020-06-01", tz="UTC")) == {"OLDUSDT"}
    assert active_universe(lifecycles, pd.Timestamp("2023-01-01", tz="UTC")) == {"NEWUSDT"}


def test_dataset_digest_is_order_invariant_and_manifest_is_point_in_time():
    a, b = frame(), frame("2020-02-01")
    assert dataset_digest({"A": a, "B": b}) == dataset_digest({"B": b, "A": a})
    manifest = build_manifest({"A": a}, "binance-vision", "universe.csv")
    assert manifest["point_in_time"] is True
    assert len(manifest["sha256"]) == 64


def test_experiment_id_is_deterministic_and_registry_is_append_only(tmp_path):
    params = {"ema": 50}
    split = {"fold": 1}
    exp_id = stable_experiment_id("a" * 64, "deadbeef", params, split)
    assert exp_id == stable_experiment_id("a" * 64, "deadbeef", params, split)
    record = make_record("a" * 64, "deadbeef", params, split, {"sharpe": 1.2}, "COMPLETE")
    assert record.experiment_id == exp_id
    registry = JsonlExperimentRegistry(tmp_path / "experiments.jsonl")
    registry.append(record)
    with pytest.raises(ValueError):
        registry.append(record)
    saved = json.loads((tmp_path / "experiments.jsonl").read_text().strip())
    assert saved["experiment_id"] == exp_id


def test_holdout_is_frozen_at_end_and_non_overlapping():
    idx = pd.date_range("2018-01-01", "2025-01-01", freq="D", tz="UTC")
    research, holdout = freeze_holdout(idx, 365)
    assert research.max() < holdout.min()
    assert holdout.max() == idx.max()
