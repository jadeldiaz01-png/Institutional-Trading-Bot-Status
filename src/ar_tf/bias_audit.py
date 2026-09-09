from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_yaml(path: str | Path) -> dict[str, Any]:
    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected mapping in {path}")
    return value


def audit_frozen_dataset(dataset_dir: str | Path, folds_path: str | Path) -> dict[str, Any]:
    """G4 bias audit over the certified dataset without reading final-holdout returns.

    The audit is intentionally structural. It validates timestamp/lifecycle/OHLCV
    invariants and the research/holdout boundary, but it never computes a signal,
    return, feature, label, metric, or model result inside the final holdout.
    """
    root = Path(dataset_dir)
    cert = json.loads((root / "dataset-freeze-certificate.json").read_text(encoding="utf-8"))
    folds = _load_yaml(folds_path)
    research_end = pd.Timestamp(folds["research_window"]["end"])
    holdout_start = pd.Timestamp(folds["holdout"]["start"])
    if research_end.tzinfo is None:
        research_end = research_end.tz_localize("UTC")
    if holdout_start.tzinfo is None:
        holdout_start = holdout_start.tz_localize("UTC")

    reasons: list[str] = []
    required = {
        "decision": "FROZEN_DATASET",
        "frozen": True,
        "unresolved_count": 0,
        "unresolved_gap_count": 0,
        "unresolved_anomaly_count": 0,
        "invalid_checksum_evidence_count": 0,
        "lifecycle_binding_verified": True,
        "source_plan_binding_verified": True,
        "holdout_evaluated": False,
    }
    for key, expected in required.items():
        if cert.get(key) != expected:
            reasons.append(f"CERTIFICATE_{key.upper()}_FAILED")

    if folds.get("holdout", {}).get("opened") is not False:
        reasons.append("HOLDOUT_NOT_SEALED")
    if holdout_start <= research_end:
        reasons.append("INVALID_RESEARCH_HOLDOUT_BOUNDARY")

    files = sorted((root / "market").glob("*.csv"))
    if len(files) != int(cert.get("market_episode_count", -1)):
        reasons.append("MARKET_EPISODE_FILE_COUNT_MISMATCH")

    rows_checked = 0
    research_rows = 0
    holdout_rows_seen_structurally = 0
    for path in files:
        df = pd.read_csv(path)
        expected_cols = {"timestamp", "symbol", "episode_id", "open", "high", "low", "close", "volume", "quote_volume", "trade_count"}
        if set(df.columns) != expected_cols:
            reasons.append(f"SCHEMA_MISMATCH:{path.name}")
            continue
        if df.empty:
            reasons.append(f"EMPTY_EPISODE:{path.name}")
            continue
        ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        if ts.isna().any() or not ts.is_monotonic_increasing or ts.duplicated().any():
            reasons.append(f"TIMESTAMP_INTEGRITY:{path.name}")
        if not ((ts.dt.hour == 0) & (ts.dt.minute == 0) & (ts.dt.second == 0)).all():
            reasons.append(f"NON_DAILY_BOUNDARY:{path.name}")
        if df["symbol"].nunique(dropna=False) != 1 or df["episode_id"].nunique(dropna=False) != 1:
            reasons.append(f"IDENTITY_NOT_CONSTANT:{path.name}")
        numeric = df[["open", "high", "low", "close", "volume", "quote_volume", "trade_count"]].apply(pd.to_numeric, errors="coerce")
        if numeric.isna().any(axis=None):
            reasons.append(f"NON_NUMERIC_OHLCV:{path.name}")
        if ((numeric[["open", "high", "low", "close"]]) <= 0).any(axis=None):
            reasons.append(f"NON_POSITIVE_PRICE:{path.name}")
        if (numeric[["volume", "quote_volume", "trade_count"]] < 0).any(axis=None):
            reasons.append(f"NEGATIVE_ACTIVITY:{path.name}")
        if (numeric["high"] < numeric[["open", "close", "low"]].max(axis=1)).any():
            reasons.append(f"HIGH_INVARIANT:{path.name}")
        if (numeric["low"] > numeric[["open", "close", "high"]].min(axis=1)).any():
            reasons.append(f"LOW_INVARIANT:{path.name}")

        rows_checked += len(df)
        research_rows += int((ts <= research_end).sum())
        # Count timestamps only. Never read/aggregate holdout returns or values.
        holdout_rows_seen_structurally += int((ts >= holdout_start).sum())

    result = {
        "schema_version": "1.0.0",
        "gate": "G4",
        "decision": "PASS" if not reasons else "FAIL",
        "reasons": sorted(set(reasons)),
        "dataset_sha256": cert.get("dataset_sha256"),
        "lifecycle_sha256": cert.get("verified_lifecycle_sha256"),
        "dataset_certificate_sha256": sha256_file(root / "dataset-freeze-certificate.json"),
        "fold_definition_sha256": sha256_file(folds_path),
        "market_episode_count": len(files),
        "rows_checked": rows_checked,
        "research_rows": research_rows,
        "holdout_rows_seen_structurally": holdout_rows_seen_structurally,
        "holdout_values_evaluated": False,
        "holdout_opened": False,
        "lookahead_policy": "ALL_SIGNALS_FEATURES_LABELS_AND_EXECUTION_MUST_BE_CAUSAL_AND_ONE_BAR_DELAYED",
        "survivorship_policy": "POINT_IN_TIME_LIFECYCLE_EPISODES_INCLUDE_DEAD_AND_DELISTED_ASSETS",
        "selection_window_end": research_end.isoformat(),
        "final_holdout_start": holdout_start.isoformat(),
    }
    return result


def write_bias_audit(result: dict[str, Any], output: str | Path) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
