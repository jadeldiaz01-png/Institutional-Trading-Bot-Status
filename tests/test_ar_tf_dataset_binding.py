import json
from pathlib import Path

import pytest

from ar_tf.dataset_binding import bind_frozen_dataset, assert_trial_binding


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _certificate(**overrides):
    base = {
        "decision": "FROZEN_DATASET",
        "frozen": True,
        "unresolved_count": 0,
        "unresolved_anomaly_count": 0,
        "unresolved_gap_count": 0,
        "invalid_checksum_evidence_count": 0,
        "source_plan_binding_verified": True,
        "lifecycle_binding_verified": True,
        "dataset_sha256": "a" * 64,
        "verified_lifecycle_sha256": "b" * 64,
        "code_sha": "c" * 64,
        "holdout_evaluated": False,
        "paper_authorized": False,
        "testnet_authorized": False,
        "live_authorized": False,
    }
    base.update(overrides)
    return base


def test_frozen_dataset_binding_accepts_only_certified_identity(tmp_path):
    cert = _write(tmp_path / "certificate.json", json.dumps(_certificate(), sort_keys=True))
    cfg = _write(tmp_path / "config.yaml", "trial_count: 407\n")
    folds = _write(tmp_path / "folds.json", '{"scheme":"rolling_oos"}')
    binding = bind_frozen_dataset(cert, config_path=cfg, fold_definition_path=folds)
    assert binding.dataset_sha256 == "a" * 64
    assert binding.lifecycle_sha256 == "b" * 64
    assert len(binding.config_sha256) == 64
    assert len(binding.fold_definition_sha256) == 64
    assert len(binding.certificate_sha256) == 64


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("decision", "NO_GO"),
        ("frozen", False),
        ("unresolved_count", 1),
        ("unresolved_gap_count", 1),
        ("unresolved_anomaly_count", 1),
        ("invalid_checksum_evidence_count", 1),
        ("source_plan_binding_verified", False),
        ("lifecycle_binding_verified", False),
        ("holdout_evaluated", True),
        ("paper_authorized", True),
    ],
)
def test_preflight_fails_closed_on_non_certified_dataset(tmp_path, field, value):
    cert = _certificate(**{field: value})
    cert_path = _write(tmp_path / "certificate.json", json.dumps(cert, sort_keys=True))
    cfg = _write(tmp_path / "config.yaml", "trial_count: 407\n")
    folds = _write(tmp_path / "folds.json", '{}')
    with pytest.raises(ValueError):
        bind_frozen_dataset(cert_path, config_path=cfg, fold_definition_path=folds)


def test_trial_binding_rejects_any_identity_drift(tmp_path):
    cert_path = _write(tmp_path / "certificate.json", json.dumps(_certificate(), sort_keys=True))
    cfg = _write(tmp_path / "config.yaml", "trial_count: 407\n")
    folds = _write(tmp_path / "folds.json", '{}')
    binding = bind_frozen_dataset(cert_path, config_path=cfg, fold_definition_path=folds)
    trial = {
        "dataset_sha256": binding.dataset_sha256,
        "lifecycle_sha256": binding.lifecycle_sha256,
        "code_sha": binding.code_sha,
        "config_sha256": binding.config_sha256,
        "fold_definition_sha256": binding.fold_definition_sha256,
        "holdout_evaluated": False,
    }
    assert_trial_binding(binding, trial)
    drifted = dict(trial, config_sha256="0" * 64)
    with pytest.raises(ValueError, match="config_sha256"):
        assert_trial_binding(binding, drifted)
