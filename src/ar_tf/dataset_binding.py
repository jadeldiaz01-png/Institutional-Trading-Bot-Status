from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
from pathlib import Path


@dataclass(frozen=True)
class FrozenDatasetBinding:
    dataset_sha256: str
    lifecycle_sha256: str
    code_sha: str
    config_sha256: str
    fold_definition_sha256: str
    certificate_sha256: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _require_sha256(name: str, value: object) -> str:
    text = str(value or "")
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text.lower()):
        raise ValueError(f"{name} must be a 64-character SHA-256 hex digest")
    return text.lower()


def bind_frozen_dataset(
    certificate_path: str | Path,
    *,
    config_path: str | Path,
    fold_definition_path: str | Path,
    expected_dataset_sha256: str | None = None,
    expected_lifecycle_sha256: str | None = None,
) -> FrozenDatasetBinding:
    """Create the only binding accepted by the preregistered tournament.

    The function is intentionally fail-closed. A provisional/NO_GO dataset,
    opened holdout, unresolved anomaly/gap, invalid checksum evidence, missing
    source/lifecycle binding, or hash mismatch aborts before any trial may run.
    """
    cert_path = Path(certificate_path)
    cert = json.loads(cert_path.read_text(encoding="utf-8"))

    required_true = {
        "frozen": cert.get("frozen"),
        "source_plan_binding_verified": cert.get("source_plan_binding_verified"),
        "lifecycle_binding_verified": cert.get("lifecycle_binding_verified"),
    }
    if cert.get("decision") != "FROZEN_DATASET":
        raise ValueError("dataset certificate decision must be FROZEN_DATASET")
    for name, value in required_true.items():
        if value is not True:
            raise ValueError(f"dataset certificate requires {name}=true")

    zero_fields = (
        "unresolved_count",
        "unresolved_anomaly_count",
        "unresolved_gap_count",
        "invalid_checksum_evidence_count",
    )
    for name in zero_fields:
        if int(cert.get(name, -1)) != 0:
            raise ValueError(f"dataset certificate requires {name}=0")

    if cert.get("holdout_evaluated") is not False:
        raise ValueError("final holdout must remain unopened before tournament")
    for name in ("paper_authorized", "testnet_authorized", "live_authorized"):
        if cert.get(name) is not False:
            raise ValueError(f"dataset certificate requires {name}=false")

    dataset_sha = _require_sha256("dataset_sha256", cert.get("dataset_sha256"))
    lifecycle_sha = _require_sha256("verified_lifecycle_sha256", cert.get("verified_lifecycle_sha256"))
    code_sha = _require_sha256("code_sha", cert.get("code_sha"))

    if expected_dataset_sha256 and dataset_sha != _require_sha256("expected_dataset_sha256", expected_dataset_sha256):
        raise ValueError("dataset SHA does not match the approved frozen dataset")
    if expected_lifecycle_sha256 and lifecycle_sha != _require_sha256("expected_lifecycle_sha256", expected_lifecycle_sha256):
        raise ValueError("lifecycle SHA does not match the approved frozen lifecycle")

    return FrozenDatasetBinding(
        dataset_sha256=dataset_sha,
        lifecycle_sha256=lifecycle_sha,
        code_sha=code_sha,
        config_sha256=_sha256_file(config_path),
        fold_definition_sha256=_sha256_file(fold_definition_path),
        certificate_sha256=_sha256_file(cert_path),
    )


def assert_trial_binding(binding: FrozenDatasetBinding, trial_record: dict) -> None:
    """Reject a trial record unless all immutable research identities match."""
    required = binding.to_dict()
    for name in (
        "dataset_sha256",
        "lifecycle_sha256",
        "code_sha",
        "config_sha256",
        "fold_definition_sha256",
    ):
        if str(trial_record.get(name, "")) != required[name]:
            raise ValueError(f"trial binding mismatch: {name}")
    if trial_record.get("holdout_evaluated") is not False:
        raise ValueError("trial record must preserve holdout_evaluated=false")
