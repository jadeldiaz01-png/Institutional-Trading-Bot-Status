from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REQUIRED_DOMAINS = (
    "dataset", "quantitative", "execution", "risk", "security",
    "supply_chain", "reliability", "observability", "governance", "finops",
)
STAGES = ("RESEARCH","VERIFIED_BACKTEST","PAPER","TESTNET","SHADOW","LIVE_PILOT","SCALED_LIVE")

@dataclass(frozen=True)
class ReadinessResult:
    manifest: dict[str, Any]
    canonical_sha256: str


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def _evidence(status: str = "MISSING", artifacts: list[str] | None = None, sha256: str | None = None) -> dict[str, Any]:
    return {"status": status, "artifacts": artifacts or [], "sha256": sha256}


def evaluate_readiness(*, source_commit_sha: str, dataset_certificate: dict[str, Any] | None = None,
                       evidence: dict[str, dict[str, Any]] | None = None,
                       gates: list[dict[str, Any]] | None = None) -> ReadinessResult:
    """Build a deterministic, fail-closed readiness manifest.

    No probabilistic model can authorize capital. Missing/failed blocking evidence => NO_GO.
    Dataset evidence passes only with a FROZEN_DATASET certificate and zero unresolved defects.
    """
    evidence = dict(evidence or {})
    for domain in REQUIRED_DOMAINS:
        evidence.setdefault(domain, _evidence())

    if dataset_certificate:
        ok = (
            dataset_certificate.get("decision") == "FROZEN_DATASET"
            and dataset_certificate.get("unresolved_count") == 0
            and dataset_certificate.get("unresolved_gap_count") == 0
            and dataset_certificate.get("invalid_checksum_evidence_count") == 0
            and dataset_certificate.get("holdout_evaluated") is False
        )
        evidence["dataset"] = _evidence(
            "PASS" if ok else "FAIL",
            ["dataset-freeze-certificate.json"],
            dataset_certificate.get("dataset_sha256"),
        )

    gates = list(gates or [])
    blocking_failure = any(g.get("blocking", True) and g.get("status") != "PASS" for g in gates)
    missing_domain = any(evidence[d]["status"] not in ("PASS", "NOT_APPLICABLE") for d in REQUIRED_DOMAINS)

    # Research is the only safe stage until all institutional evidence is present.
    stage = "RESEARCH"
    decision = "NO_GO"
    if not blocking_failure and not missing_domain:
        # Even a fully populated infrastructure manifest cannot skip scientific holdout governance.
        decision = "FROZEN_HOLDOUT_CANDIDATE"

    manifest = {
        "schema_version": "2026-09-01",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha,
        "stage": stage,
        "decision": decision,
        "evidence": evidence,
        "gates": gates,
        "authorizations": {"paper": False, "testnet": False, "live_pilot": False, "scaled_live": False},
    }
    return ReadinessResult(manifest, canonical_sha256(manifest))


def write_readiness(result: ReadinessResult, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "production-readiness-manifest.json").write_text(json.dumps(result.manifest, indent=2, sort_keys=True) + "\n")
    (out_dir / "production-readiness-manifest.sha256").write_text(result.canonical_sha256 + "\n")
