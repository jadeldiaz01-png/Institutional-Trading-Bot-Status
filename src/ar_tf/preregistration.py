from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .trial_registry import load_and_build_registry, write_registry


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_preregistration(
    *,
    dataset_binding_path: str | Path,
    registry_spec_path: str | Path,
    strategy_config_path: str | Path,
    folds_path: str | Path,
    source_commit_sha: str,
) -> dict[str, Any]:
    binding = json.loads(Path(dataset_binding_path).read_text(encoding="utf-8"))
    if binding.get("decision") != "FROZEN_DATASET" or binding.get("frozen") is not True:
        raise ValueError("dataset binding is not FROZEN_DATASET")
    for key in ("unresolved_count", "unresolved_gap_count", "unresolved_anomaly_count", "invalid_checksum_evidence_count"):
        if binding.get(key) != 0:
            raise ValueError(f"dataset binding failed {key}")
    if binding.get("holdout_evaluated") is not False:
        raise ValueError("holdout already evaluated")
    if binding.get("source_plan_binding_verified") is not True or binding.get("lifecycle_binding_verified") is not True:
        raise ValueError("dataset binding verification failed")

    strategy_config_sha256 = sha256_file(strategy_config_path)
    fold_definition_sha256 = sha256_file(folds_path)
    registry_spec_sha256 = sha256_file(registry_spec_path)
    dataset_binding_sha256 = sha256_file(dataset_binding_path)

    registry = load_and_build_registry(
        registry_spec_path,
        dataset_sha256=binding["dataset_sha256"],
        lifecycle_sha256=binding["verified_lifecycle_sha256"],
        source_commit_sha=source_commit_sha,
        strategy_config_sha256=strategy_config_sha256,
        fold_definition_sha256=fold_definition_sha256,
    )
    if registry["trial_count"] != 407:
        raise ValueError(f"expected exactly 407 preregistered trials, got {registry['trial_count']}")

    manifest = {
        "schema_version": "1.0.0",
        "gate": "G5",
        "decision": "PASS",
        "state": "PREREGISTERED_NOT_EXECUTED",
        "source_commit_sha": source_commit_sha,
        "dataset_sha256": binding["dataset_sha256"],
        "lifecycle_sha256": binding["verified_lifecycle_sha256"],
        "dataset_binding_sha256": dataset_binding_sha256,
        "strategy_config_sha256": strategy_config_sha256,
        "fold_definition_sha256": fold_definition_sha256,
        "registry_spec_sha256": registry_spec_sha256,
        "trial_registry_sha256": registry["registry_sha256"],
        "trial_count": registry["trial_count"],
        "all_attempts_count_for_multiplicity": True,
        "common_oos_folds": True,
        "holdout_evaluated": False,
        "paper_authorized": False,
        "testnet_authorized": False,
        "live_authorized": False,
    }
    return {"manifest": manifest, "registry": registry}


def write_preregistration(bundle: dict[str, Any], output_dir: str | Path) -> None:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    write_registry(bundle["registry"], root / "preregistered-trial-registry.json")
    (root / "g5-preregistration-manifest.json").write_text(
        json.dumps(bundle["manifest"], indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
