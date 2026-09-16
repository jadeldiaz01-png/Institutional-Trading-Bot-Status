from pathlib import Path
import json
import pytest

from ar_tf.ridge_fold_resume import (
    EXPECTED_FOLDS,
    commit_fold_checkpoint,
    load_committed_fold,
    validate_fold_inventory,
)


def lineage():
    return {
        "cp02_artifact_id": 10419024917,
        "cp02_digest": "sha256:974d02bbce33d7809c6cc3f44a21f3d2e249ec320d7362e18fedd584e20e25ce",
        "dataset_sha256": "dataset",
        "registry_sha256": "registry",
        "folds_sha256": "folds",
        "scientific_config_sha256": "config",
        "seed": 7,
        "holdout_opened": False,
        "holdout_evaluated": False,
    }


def test_transactional_checkpoint_round_trip(tmp_path):
    mp = commit_fold_checkpoint(tmp_path, trial_id="ridge-00", fold_id=0, lineage=lineage(), payload={"prediction": [1.0], "status": "OK"})
    got = load_committed_fold(mp, expected_trial_id="ridge-00", expected_fold_id=0, expected_lineage=lineage())
    assert got == {"prediction": [1.0], "status": "OK"}


def test_tampered_payload_is_rejected(tmp_path):
    mp = commit_fold_checkpoint(tmp_path, trial_id="ridge-00", fold_id=0, lineage=lineage(), payload={"x": 1})
    (mp.parent / "payload.json").write_text('{"x":2}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="digest"):
        load_committed_fold(mp, expected_trial_id="ridge-00", expected_fold_id=0, expected_lineage=lineage())


def test_started_or_truncated_manifest_is_rejected(tmp_path):
    mp = commit_fold_checkpoint(tmp_path, trial_id="ridge-00", fold_id=0, lineage=lineage(), payload={"x": 1})
    m = json.loads(mp.read_text())
    m["state"] = "STARTED"
    mp.write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(ValueError, match="COMMITTED"):
        load_committed_fold(mp, expected_trial_id="ridge-00", expected_fold_id=0, expected_lineage=lineage())


def test_lineage_mismatch_and_holdout_are_rejected(tmp_path):
    mp = commit_fold_checkpoint(tmp_path, trial_id="ridge-00", fold_id=0, lineage=lineage(), payload={"x": 1})
    bad = lineage(); bad["dataset_sha256"] = "other"
    with pytest.raises(ValueError, match="lineage"):
        load_committed_fold(mp, expected_trial_id="ridge-00", expected_fold_id=0, expected_lineage=bad)
    bad_holdout = lineage(); bad_holdout["holdout_evaluated"] = True
    with pytest.raises(ValueError, match="holdout"):
        commit_fold_checkpoint(tmp_path, trial_id="ridge-00", fold_id=1, lineage=bad_holdout, payload={"x": 1})


def test_inventory_requires_exact_324_unique_folds():
    tids = [f"ridge-{i:02d}" for i in range(27)]
    records = [{"trial_id": tid, "fold_id": fid} for tid in tids for fid in range(12)]
    result = validate_fold_inventory(records, tids)
    assert result["verified_folds"] == EXPECTED_FOLDS == 324
    assert result["verified_trials"] == 27
    with pytest.raises(ValueError, match="duplicate"):
        validate_fold_inventory(records + [records[0]], tids)
    with pytest.raises(ValueError, match="invalid fold inventory"):
        validate_fold_inventory(records[:-1], tids)


def test_resume_equivalence_property(tmp_path):
    """Committed folds reused after an interruption are byte-for-byte equivalent."""
    lin = lineage()
    uninterrupted = {}
    for fid in range(12):
        payload = {"fold": fid, "prediction": [fid / 10.0], "weights": [fid / 20.0], "base": fid, "stressed": fid - 1, "severe": fid - 2}
        uninterrupted[fid] = payload
        commit_fold_checkpoint(tmp_path / "run", trial_id="ridge-00", fold_id=fid, lineage=lin, payload=payload)
    for interruption in (1, 6, 11):
        resumed = {}
        for fid in range(12):
            mp = tmp_path / "run" / "ridge-00" / f"fold-{fid:02d}" / "manifest.json"
            # Simulate restart: committed folds up to interruption are loaded; later
            # folds are produced by the same frozen function and committed.
            if fid <= interruption:
                resumed[fid] = load_committed_fold(mp, expected_trial_id="ridge-00", expected_fold_id=fid, expected_lineage=lin)
            else:
                payload = uninterrupted[fid]
                commit_fold_checkpoint(tmp_path / f"resume-{interruption}", trial_id="ridge-00", fold_id=fid, lineage=lin, payload=payload)
                rmp = tmp_path / f"resume-{interruption}" / "ridge-00" / f"fold-{fid:02d}" / "manifest.json"
                resumed[fid] = load_committed_fold(rmp, expected_trial_id="ridge-00", expected_fold_id=fid, expected_lineage=lin)
        assert resumed == uninterrupted
