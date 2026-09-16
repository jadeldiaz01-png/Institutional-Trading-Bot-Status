from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from ar_tf.ml_trials import FoldCheckpointPause
from ar_tf.research_panel import load_research_panel
from ar_tf.ridge_resume import execute_trial, trial_at


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_output(key: str, value: str) -> None:
    output = Path(os.environ["GITHUB_OUTPUT"])
    with output.open("a", encoding="utf-8") as handle:
        handle.write(f"{key}={value}\n")


def main() -> None:
    index = int(os.environ["TRIAL_INDEX"])
    fold_id = int(os.environ["FOLD_ID"])
    if fold_id < 0 or fold_id > 11:
        raise ValueError("FOLD_ID must be in [0, 11]")

    root = Path("artifacts/g4_g13")
    registry_path = root / "preregistration/preregistered-trial-registry.json"
    folds_path = Path("config/ar_tf_oos_folds_2026.yaml")
    binding_path = Path("config/ar_tf_frozen_dataset_binding_2026.json")
    checkpoint_root = Path("artifacts/ridge_fold_checkpoints")

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    trial = trial_at(registry, index)
    trial_id = str(trial["trial_id"])
    fold_root = checkpoint_root / trial_id / f"fold-{fold_id:02d}"
    existed_before = (fold_root / "manifest.json").is_file()

    lineage = {
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
    try:
        execute_trial(
            panel=panel,
            registry=registry,
            folds_path=folds_path,
            index=index,
            checkpoint_root=checkpoint_root,
            checkpoint_lineage=lineage,
            pause_after_fold=fold_id,
        )
    except FoldCheckpointPause:
        pass
    else:
        raise RuntimeError(f"fold {fold_id} did not reach the verified checkpoint pause")

    if not (fold_root / "manifest.json").is_file() or not (fold_root / "payload.json").is_file():
        raise RuntimeError(f"fold {fold_id} checkpoint files are absent after verified pause")

    _write_output("new_fold", "false" if existed_before else "true")
    _write_output("trial_id", trial_id)
    _write_output("fold_path", str(fold_root))
    _write_output("artifact_name", f"ar-tf-ridge-fold-{index:02d}-{fold_id:02d}")


if __name__ == "__main__":
    main()
