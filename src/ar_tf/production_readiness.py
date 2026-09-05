from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .evidence_validation import validate_domain_evidence

REQUIRED_DOMAINS = (
    "dataset", "quantitative", "execution", "risk", "security",
    "supply_chain", "reliability", "observability", "governance", "finops",
)
STAGES = ("RESEARCH", "VERIFIED_BACKTEST", "PAPER", "TESTNET", "SHADOW", "LIVE_PILOT", "SCALED_LIVE")


@dataclass(frozen=True)
class ReadinessResult:
    manifest: dict[str, Any]
    canonical_sha256: str


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def _domain(status: str = "MISSING", items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"status": status, "items": items or [], "validation_reasons": []}


def _dataset_item(dataset_certificate: dict[str, Any], source_commit_sha: str) -> dict[str, Any]:
    return {
        "status": "PASS",
        "artifact": "dataset-freeze-certificate.json",
        "sha256": dataset_certificate.get("dataset_sha256"),
        "source_commit_sha": source_commit_sha,
        "issuer": "ar-tf-v1d2-data",
        "verification": "VERIFIED",
        "provenance": {"required": False, "verified": False},
    }


def evaluate_readiness(
    *,
    source_commit_sha: str,
    dataset_certificate: dict[str, Any] | None = None,
    evidence: dict[str, dict[str, Any]] | None = None,
    gates: list[dict[str, Any]] | None = None,
) -> ReadinessResult:
    """Build deterministic fail-closed institutional production-readiness evidence.

    A self-declared PASS is insufficient. Every PASS domain must contain immutable
    evidence bound to the evaluated commit and pass the evidence-validation contract.
    No probabilistic model can authorize capital.
    """
    evidence = dict(evidence or {})
    for name in REQUIRED_DOMAINS:
        evidence.setdefault(name, _domain())

    if dataset_certificate:
        dataset_ok = (
            dataset_certificate.get("decision") == "FROZEN_DATASET"
            and dataset_certificate.get("frozen") is True
            and dataset_certificate.get("unresolved_count") == 0
            and dataset_certificate.get("unresolved_anomaly_count") == 0
            and dataset_certificate.get("unresolved_gap_count") == 0
            and dataset_certificate.get("invalid_checksum_evidence_count") == 0
            and dataset_certificate.get("holdout_evaluated") is False
        )
        evidence["dataset"] = _domain(
            "PASS" if dataset_ok else "FAIL",
            [_dataset_item(dataset_certificate, source_commit_sha)] if dataset_ok else [],
        )

    validated: dict[str, dict[str, Any]] = {}
    for name in REQUIRED_DOMAINS:
        domain = dict(evidence[name])
        if domain.get("status") == "PASS":
            ok, reasons = validate_domain_evidence(domain, expected_commit_sha=source_commit_sha)
            domain["validation_reasons"] = reasons
            if not ok:
                domain["status"] = "FAIL"
        validated[name] = domain

    gates = list(gates or [])
    blocking_failure = any(g.get("blocking", True) and g.get("status") != "PASS" for g in gates)
    incomplete = any(validated[d]["status"] not in ("PASS", "NOT_APPLICABLE") for d in REQUIRED_DOMAINS)

    stage = "RESEARCH"
    decision = "NO_GO"
    if not blocking_failure and not incomplete:
        # Infrastructure completeness still cannot bypass the untouched holdout.
        decision = "FROZEN_HOLDOUT_CANDIDATE"

    manifest = {
        "schema_version": "2026-09-05",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha,
        "stage": stage,
        "decision": decision,
        "evidence": validated,
        "gates": gates,
        "authorizations": {
            "paper": False,
            "testnet": False,
            "shadow": False,
            "live_pilot": False,
            "scaled_live": False,
        },
        "governance": {
            "default_deny": True,
            "probabilistic_authorization_forbidden": True,
            "human_approval_required_for_live_capital": True,
            "missing_evidence_means_no_go": True,
        },
    }
    return ReadinessResult(manifest, canonical_sha256(manifest))


def write_readiness(result: ReadinessResult, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "production-readiness-manifest.json").write_text(
        json.dumps(result.manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "production-readiness-manifest.sha256").write_text(
        result.canonical_sha256 + "\n", encoding="utf-8"
    )
