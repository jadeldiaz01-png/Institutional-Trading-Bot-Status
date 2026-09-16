from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from ar_tf.ml_trials import FoldCheckpointPause, _fold_lineage, _folds
from ar_tf.research_panel import load_research_panel
from ar_tf.ridge_fold_resume import load_committed_fold
from ar_tf.ridge_resume import execute_trial, trial_at


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_output(key: str, value: str) -> None:
    output = Path(os.environ["GITHUB_OUTPUT"])
    with output.open("a", encoding="utf-8") as handle:
        handle.write(f"{key}={value}\n")


def _emit_outputs(*, index: int, fold_id: int, trial_id: str, fold_root: Path, new_fold: bool) -> None:
    _write_output("new_fold", "true" if new_fold else "false")
    _write_output("trial_id", trial_id)
    _write_output("fold_path", str(fold_root))
    _write_output("artifact_name", f"ar-tf-ridge-fold-{index:02d}-{fold_id:02d}")


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
    manifest_path = fold_root / "manifest.json"

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

    # Fast path for a fold already committed by an earlier attempt of the same
    # run/SHA. Validate the exact internal checkpoint contract directly instead
    # of rebuilding the full research panel merely to rediscover the same
    # payload. This is execution-only: the scientific path for a missing fold
    # remains execute_trial() -> walk_forward_predictions() unchanged.
    if manifest_path.is_file():
        folds = _folds(folds_path)
        expected_lineage = _fold_lineage(
            lineage,
            fold=folds[fold_id],
            family="ridge",
            params=trial["params"],
            seed=int(trial["seed"]),
            max_training_rows_per_fold=100_000,
        )
        payload = load_committed_fold(
            manifest_path,
            expected_trial_id=trial_id,
            expected_fold_id=fold_id,
            expected_lineage=expected_lineage,
        )
        if "rng_state_after_fold" not in payload:
            raise ValueError("checkpoint missing rng_state_after_fold")
        _emit_outputs(
            index=index,
            fold_id=fold_id,
            trial_id=trial_id,
            fold_root=fold_root,
            new_fold=False,
        )
        return

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

    if not manifest_path.is_file() or not (fold_root / "payload.json").is_file():
        raise RuntimeError(f"fold {fold_id} checkpoint files are absent after verified pause")

    _emit_outputs(
        index=index,
        fold_id=fold_id,
        trial_id=trial_id,
        fold_root=fold_root,
        new_fold=True,
    )


if __name__ == "__main__":
    main()
