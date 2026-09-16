"""Durable, fail-closed fold checkpoints for Ridge resume.

This module is deliberately science-agnostic: it persists and validates the
outputs produced by the frozen Ridge implementation. It never changes model
parameters, folds, costs, seeds, or statistical thresholds.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "1.0.0"
EXPECTED_RIDGE_TRIALS = 27
EXPECTED_FOLDS_PER_TRIAL = 12
EXPECTED_FOLDS = EXPECTED_RIDGE_TRIALS * EXPECTED_FOLDS_PER_TRIAL


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write_bytes(path: str | Path, data: bytes) -> None:
    """Commit bytes atomically on the local filesystem: tmp -> fsync -> rename."""
    dst = Path(path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{dst.name}.{os.getpid()}.tmp")
    with tmp.open("wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, dst)
    # Best-effort directory durability on POSIX.
    try:
        fd = os.open(str(dst.parent), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def commit_fold_checkpoint(
    root: str | Path,
    *,
    trial_id: str,
    fold_id: int,
    lineage: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> Path:
    """Write one COMMITTED fold checkpoint and a self-verifying manifest."""
    if not trial_id:
        raise ValueError("trial_id required")
    if fold_id < 0 or fold_id >= EXPECTED_FOLDS_PER_TRIAL:
        raise ValueError("fold_id out of range")
    if bool(lineage.get("holdout_opened")) or bool(lineage.get("holdout_evaluated")):
        raise ValueError("holdout must remain closed")

    fold_dir = Path(root) / trial_id / f"fold-{fold_id:02d}"
    payload_path = fold_dir / "payload.json"
    manifest_path = fold_dir / "manifest.json"
    payload_bytes = _canonical_json(payload) + b"\n"
    atomic_write_bytes(payload_path, payload_bytes)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "state": "COMMITTED",
        "trial_id": trial_id,
        "fold_id": fold_id,
        "payload_sha256": sha256_bytes(payload_bytes),
        "lineage": dict(lineage),
    }
    manifest_bytes = _canonical_json(manifest) + b"\n"
    atomic_write_bytes(manifest_path, manifest_bytes)
    return manifest_path


def load_committed_fold(
    manifest_path: str | Path,
    *,
    expected_trial_id: str,
    expected_fold_id: int,
    expected_lineage: Mapping[str, Any],
) -> dict[str, Any]:
    """Load a checkpoint only when state, identity, lineage and digest match."""
    mp = Path(manifest_path)
    manifest = json.loads(mp.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("state") != "COMMITTED":
        raise ValueError("checkpoint is not COMMITTED")
    if manifest.get("trial_id") != expected_trial_id or int(manifest.get("fold_id", -1)) != expected_fold_id:
        raise ValueError("checkpoint identity mismatch")
    lineage = manifest.get("lineage", {})
    if lineage != dict(expected_lineage):
        raise ValueError("checkpoint lineage mismatch")
    if bool(lineage.get("holdout_opened")) or bool(lineage.get("holdout_evaluated")):
        raise ValueError("holdout evidence forbidden")
    payload_path = mp.parent / "payload.json"
    if not payload_path.is_file():
        raise ValueError("checkpoint payload missing")
    if sha256_file(payload_path) != manifest.get("payload_sha256"):
        raise ValueError("checkpoint payload digest mismatch")
    return json.loads(payload_path.read_text(encoding="utf-8"))


def validate_fold_inventory(records: list[Mapping[str, Any]], expected_trial_ids: list[str]) -> dict[str, int]:
    """Fail closed unless the inventory proves 27 x 12 = 324 unique folds."""
    if len(expected_trial_ids) != EXPECTED_RIDGE_TRIALS or len(set(expected_trial_ids)) != EXPECTED_RIDGE_TRIALS:
        raise ValueError("expected Ridge registry must contain exactly 27 unique trials")
    expected = {(tid, fid) for tid in expected_trial_ids for fid in range(EXPECTED_FOLDS_PER_TRIAL)}
    observed = [(str(r["trial_id"]), int(r["fold_id"])) for r in records]
    if len(observed) != len(set(observed)):
        raise ValueError("duplicate fold checkpoints")
    observed_set = set(observed)
    missing = expected - observed_set
    unexpected = observed_set - expected
    if missing or unexpected or len(observed_set) != EXPECTED_FOLDS:
        raise ValueError(f"invalid fold inventory missing={len(missing)} unexpected={len(unexpected)} observed={len(observed_set)}")
    return {"expected_folds": EXPECTED_FOLDS, "verified_folds": len(observed_set), "expected_trials": 27, "verified_trials": 27}
