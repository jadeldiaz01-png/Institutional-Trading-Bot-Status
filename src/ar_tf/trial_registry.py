from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

import yaml


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _grid(params: dict[str, list[Any]]) -> list[dict[str, Any]]:
    if not params:
        return [{}]
    keys = sorted(params)
    values = [params[k] for k in keys]
    if any(not isinstance(v, list) or not v for v in values):
        raise ValueError("every parameter grid entry must be a non-empty list")
    return [dict(zip(keys, combo, strict=True)) for combo in itertools.product(*values)]


def build_registry(
    spec: dict[str, Any],
    *,
    dataset_sha256: str,
    lifecycle_sha256: str,
    source_commit_sha: str,
) -> dict[str, Any]:
    """Expand a bounded preregistered search space into immutable trial identities.

    This function deliberately refuses an unfrozen/unknown dataset identity and
    counts every parameter/seed combination before any model is executed.
    """
    for name, value, length in (
        ("dataset_sha256", dataset_sha256, 64),
        ("lifecycle_sha256", lifecycle_sha256, 64),
        ("source_commit_sha", source_commit_sha, 40),
    ):
        if len(value) != length or any(c not in "0123456789abcdef" for c in value.lower()):
            raise ValueError(f"invalid {name}")

    trials: list[dict[str, Any]] = []
    seen: set[str] = set()
    for family_spec in spec.get("families", []):
        family = str(family_spec["family"])
        tier = str(family_spec.get("tier", "UNSPECIFIED"))
        data_track = str(family_spec.get("data_track", "spot_daily_ohlcv"))
        seeds = list(family_spec.get("seeds", [7]))
        parameter_sets = _grid(dict(family_spec.get("parameters", {})))
        for params in parameter_sets:
            for seed in seeds:
                identity_payload = {
                    "dataset_sha256": dataset_sha256,
                    "lifecycle_sha256": lifecycle_sha256,
                    "family": family,
                    "tier": tier,
                    "data_track": data_track,
                    "params": params,
                    "seed": int(seed),
                }
                digest = canonical_sha256(identity_payload)
                trial_id = f"{family}:{digest[:16]}"
                if trial_id in seen:
                    raise ValueError(f"duplicate trial identity: {trial_id}")
                seen.add(trial_id)
                trials.append({"trial_id": trial_id, "trial_sha256": digest, **identity_payload})

    trials.sort(key=lambda x: x["trial_id"])
    registry_core = {
        "schema_version": "1.0.0",
        "state": "PREREGISTERED_NOT_EXECUTED",
        "dataset_sha256": dataset_sha256,
        "lifecycle_sha256": lifecycle_sha256,
        "source_commit_sha": source_commit_sha,
        "holdout_evaluated": False,
        "trial_count": len(trials),
        "trials": trials,
    }
    return {**registry_core, "registry_sha256": canonical_sha256(registry_core)}


def load_and_build_registry(
    spec_path: str | Path,
    *,
    dataset_sha256: str,
    lifecycle_sha256: str,
    source_commit_sha: str,
) -> dict[str, Any]:
    spec = yaml.safe_load(Path(spec_path).read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        raise ValueError("registry specification must be a mapping")
    return build_registry(
        spec,
        dataset_sha256=dataset_sha256,
        lifecycle_sha256=lifecycle_sha256,
        source_commit_sha=source_commit_sha,
    )


def write_registry(registry: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
