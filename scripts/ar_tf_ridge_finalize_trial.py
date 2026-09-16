from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from ar_tf.research_panel import load_research_panel
from ar_tf.ridge_resume import execute_trial, write_trial


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    index = int(os.environ["TRIAL_INDEX"])
    root = Path("artifacts/g4_g13")
    registry_path = root / "preregistration/preregistered-trial-registry.json"
    folds_path = Path("config/ar_tf_oos_folds_2026.yaml")
    binding_path = Path("config/ar_tf_frozen_dataset_binding_2026.json")
    checkpoint_root = Path("artifacts/ridge_fold_checkpoints")

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    checkpoint_lineage = {
        "parent_checkpoint_sha256": os.environ["CP02_ARTIFACT_DIGEST"].split(":", 1)[1],
        "source_commit_sha": os.environ["SOURCE_SHA"],
        "dataset_sha256": binding["dataset_sha256"],
        "registry_sha256": _sha(registry_path),
        "folds_sha256": _sha(folds_path),
        "scientific_config_sha256": _sha(binding_path),
        "holdout_opened": False,
        "holdout_evaluated": False,
    }
    panel = load_research_panel(root / "frozen_dataset", folds_path)
    result = execute_trial(
        panel=panel,
        registry=registry,
        folds_path=folds_path,
        index=index,
        checkpoint_root=checkpoint_root,
        checkpoint_lineage=checkpoint_lineage,
    )
    if result["failure"] is not None:
        raise RuntimeError(f"Ridge trial failed after 12 verified fold checkpoints: {result['failure']}")

    write_trial(
        result,
        Path("ridge-trial"),
        {
            "parent_checkpoint_sha256": checkpoint_lineage["parent_checkpoint_sha256"],
            "source_commit_sha": checkpoint_lineage["source_commit_sha"],
            "dataset_sha256": checkpoint_lineage["dataset_sha256"],
            "registry_sha256": checkpoint_lineage["registry_sha256"],
            "folds_sha256": checkpoint_lineage["folds_sha256"],
            "config_sha256": checkpoint_lineage["scientific_config_sha256"],
        },
    )


if __name__ == "__main__":
    main()
