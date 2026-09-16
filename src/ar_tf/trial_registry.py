from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

import yaml


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _grid(params: dict[str, list[Any]]) -> list[dict[str, Any]]:
    if not params:
        return [{}]
    keys = sorted(params)
    values = [params[k] for k in keys]
    if any(not isinstance(v, list) or not v for v in values):
        raise ValueError("every parameter grid entry must be a non-empty list")
    return [dict(zip(keys, combo, strict=True)) for combo in itertools.product(*values)]


def _hex(value: str, *, length: int, name: str) -> str:
    normalized = str(value).lower()
    if len(normalized) != length or any(c not in "0123456789abcdef" for c in normalized):
        raise ValueError(f"invalid {name}")
    return normalized


def build_registry(
    spec: dict[str, Any],
    *,
    dataset_sha256: str,
    lifecycle_sha256: str,
    source_commit_sha: str,
    strategy_config_sha256: str | None = None,
    fold_definition_sha256: str | None = None,
) -> dict[str, Any]:
    """Expand the bounded search space before execution and bind it to frozen research identity.

    `strategy_config_sha256` and `fold_definition_sha256` are optional only for
    backwards-compatible unit tests. Production preregistration MUST supply both.
    """
    dataset_sha256 = _hex(dataset_sha256, length=64, name="dataset_sha256")
    lifecycle_sha256 = _hex(lifecycle_sha256, length=64, name="lifecycle_sha256")
    source_commit_sha = _hex(source_commit_sha, length=40, name="source_commit_sha")
    if strategy_config_sha256 is not None:
        strategy_config_sha256 = _hex(strategy_config_sha256, length=64, name="strategy_config_sha256")
    if fold_definition_sha256 is not None:
        fold_definition_sha256 = _hex(fold_definition_sha256, length=64, name="fold_definition_sha256")

    policy = dict(spec.get("policy", {}))
    max_trials = int(policy.get("max_total_registered_trials", 500))
    if max_trials < 1:
        raise ValueError("max_total_registered_trials must be positive")

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
                identity = {
                    "dataset_sha256": dataset_sha256,
                    "lifecycle_sha256": lifecycle_sha256,
                    "source_commit_sha": source_commit_sha,
                    "strategy_config_sha256": strategy_config_sha256,
                    "fold_definition_sha256": fold_definition_sha256,
                    "family": family,
                    "tier": tier,
                    "data_track": data_track,
                    "params": params,
                    "seed": int(seed),
                }
                digest = canonical_sha256(identity)
                trial_id = f"{family}:{digest[:16]}"
                if trial_id in seen:
                    raise ValueError(f"duplicate trial identity: {trial_id}")
                seen.add(trial_id)
                trials.append({"trial_id": trial_id, "trial_sha256": digest, **identity})
                if len(trials) > max_trials:
                    raise ValueError(f"preregistered trial budget exceeded: {len(trials)} > {max_trials}")

    trials.sort(key=lambda x: x["trial_id"])
    core = {
        "schema_version": "1.1.0",
        "state": "PREREGISTERED_NOT_EXECUTED",
        "dataset_sha256": dataset_sha256,
        "lifecycle_sha256": lifecycle_sha256,
        "source_commit_sha": source_commit_sha,
        "strategy_config_sha256": strategy_config_sha256,
        "fold_definition_sha256": fold_definition_sha256,
        "holdout_evaluated": False,
        "trial_budget": max_trials,
        "trial_count": len(trials),
        "trials": trials,
    }
    return {**core, "registry_sha256": canonical_sha256(core)}


def load_and_build_registry(
    spec_path: str | Path,
    *,
    dataset_sha256: str,
    lifecycle_sha256: str,
    source_commit_sha: str,
    strategy_config_sha256: str | None = None,
    fold_definition_sha256: str | None = None,
) -> dict[str, Any]:
    spec = yaml.safe_load(Path(spec_path).read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        raise ValueError("registry specification must be a mapping")
    return build_registry(
        spec,
        dataset_sha256=dataset_sha256,
        lifecycle_sha256=lifecycle_sha256,
        source_commit_sha=source_commit_sha,
        strategy_config_sha256=strategy_config_sha256,
        fold_definition_sha256=fold_definition_sha256,
    )


def write_registry(registry: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
