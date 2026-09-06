from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .evidence_validation import validate_domain_evidence

SCHEMA_VERSION = "2026-09-06"
STAGES = ("RESEARCH", "VERIFIED_BACKTEST", "PAPER", "TESTNET", "SHADOW", "LIVE_PILOT", "SCALED_LIVE")
REQUIRED_DOMAINS = (
    "repository", "dataset", "quantitative", "execution", "risk", "reconciliation",
    "security", "secrets_identity", "supply_chain", "cicd", "observability",
    "reliability", "backup_restore", "governance", "finops",
)

GATE_NAMES = {
    "G0": "Repository Integrity", "G1": "Data Integrity", "G2": "Point-in-Time Universe",
    "G3": "Dataset Freeze", "G4": "Bias Audit", "G5": "Strategy Preregistration",
    "G6": "Backtest Correctness", "G7": "OOS Validation", "G8": "Statistical Validation",
    "G9": "Cost Stress", "G10": "Robustness", "G11": "Regime Analysis",
    "G12": "Liquidity/Capacity", "G13": "Portfolio Construction", "G14": "Risk Engine",
    "G15": "Order Lifecycle", "G16": "OMS/EMS", "G17": "Exchange Adapter",
    "G18": "Idempotency", "G19": "Reconciliation", "G20": "Security",
    "G21": "Secrets/Identity", "G22": "Supply Chain", "G23": "CI/CD",
    "G24": "Observability", "G25": "Resilience", "G26": "Backup/Restore",
    "G27": "PAPER", "G28": "TESTNET", "G29": "SHADOW", "G30": "LIVE_PILOT",
    "G31": "Forward Evidence", "G32": "Production Reconciliation",
}
GATE_IDS = tuple(GATE_NAMES)

CERTIFICATION_KEYS = (
    "DATA_VERIFIED", "EDGE_VERIFIED", "EXECUTION_VERIFIED", "RISK_VERIFIED",
    "RECONCILIATION_VERIFIED", "SECURITY_VERIFIED", "PRODUCTION_INFRASTRUCTURE_VERIFIED",
    "TESTNET_VERIFIED", "SHADOW_VERIFIED", "LIVE_PILOT_VERIFIED",
    "LIVE_PRODUCTION_READY_VERIFIED",
)


@dataclass(frozen=True)
class ReadinessResult:
    manifest: dict[str, Any]
    canonical_sha256: str


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def _domain(status: str = "MISSING", items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"status": status, "items": items or [], "validation_reasons": []}


def _default_gate(gate_id: str) -> dict[str, Any]:
    return {
        "id": gate_id,
        "name": GATE_NAMES[gate_id],
        "status": "BLOCKED",
        "blocking": True,
        "evidence": [],
        "blocker": "missing_verifiable_evidence",
    }


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


def _dataset_is_frozen(c: dict[str, Any]) -> bool:
    return bool(
        c.get("decision") == "FROZEN_DATASET"
        and c.get("frozen") is True
        and c.get("unresolved_count") == 0
        and c.get("unresolved_anomaly_count") == 0
        and c.get("unresolved_gap_count") == 0
        and c.get("invalid_checksum_evidence_count") == 0
        and c.get("lifecycle_binding_verified") is True
        and c.get("source_plan_binding_verified") is True
        and c.get("holdout_evaluated") is False
        and isinstance(c.get("dataset_sha256"), str)
        and len(c["dataset_sha256"]) == 64
    )


def _normalize_gates(gates: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    supplied = {str(g.get("id")): dict(g) for g in (gates or []) if g.get("id") in GATE_NAMES}
    out: list[dict[str, Any]] = []
    for gid in GATE_IDS:
        gate = _default_gate(gid)
        if gid in supplied:
            gate.update(supplied[gid])
            gate["name"] = GATE_NAMES[gid]
            if gate.get("status") not in {"PASS", "FAIL", "BLOCKED"}:
                gate["status"] = "FAIL"
                gate["blocker"] = "invalid_gate_status"
            gate.setdefault("evidence", [])
        out.append(gate)
    return out


def _gate_pass(gates: dict[str, dict[str, Any]], *ids: str) -> bool:
    return all(gates[i]["status"] == "PASS" for i in ids)


def evaluate_readiness(
    *,
    source_commit_sha: str,
    dataset_certificate: dict[str, Any] | None = None,
    evidence: dict[str, dict[str, Any]] | None = None,
    gates: list[dict[str, Any]] | None = None,
    identities: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> ReadinessResult:
    """Build an evidence-bound, deterministic and fail-closed readiness manifest.

    PASS is never inferred from code presence. Every PASS evidence domain must validate
    against immutable artifacts bound to the evaluated commit. Gates not supplied with
    evidence remain BLOCKED. No agent/model output can authorize capital.
    """
    if len(source_commit_sha) != 40 or any(c not in "0123456789abcdef" for c in source_commit_sha):
        raise ValueError("source_commit_sha must be a lowercase 40-hex Git SHA")

    evidence = {k: dict(v) for k, v in (evidence or {}).items()}
    for name in REQUIRED_DOMAINS:
        evidence.setdefault(name, _domain())

    dataset_ok = False
    if dataset_certificate is not None:
        dataset_ok = _dataset_is_frozen(dataset_certificate)
        evidence["dataset"] = _domain(
            "PASS" if dataset_ok else "FAIL",
            [_dataset_item(dataset_certificate, source_commit_sha)] if dataset_ok else [],
        )

    validated: dict[str, dict[str, Any]] = {}
    for name in REQUIRED_DOMAINS:
        domain = dict(evidence[name])
        domain.setdefault("items", [])
        domain.setdefault("validation_reasons", [])
        if domain.get("status") == "PASS":
            ok, reasons = validate_domain_evidence(domain, expected_commit_sha=source_commit_sha)
            domain["validation_reasons"] = reasons
            if not ok:
                domain["status"] = "FAIL"
        elif domain.get("status") not in {"FAIL", "MISSING", "NOT_APPLICABLE"}:
            domain["status"] = "FAIL"
            domain["validation_reasons"] = ["invalid_domain_status"]
        validated[name] = domain

    normalized = _normalize_gates(gates)
    gate_map = {g["id"]: g for g in normalized}

    # Dataset certificate is authoritative for the data-freeze gates only.
    if dataset_ok:
        for gid in ("G1", "G3"):
            gate_map[gid].update({
                "status": "PASS",
                "blocker": None,
                "evidence": ["dataset-freeze-certificate.json"],
            })
    elif dataset_certificate is not None:
        for gid in ("G1", "G3"):
            gate_map[gid].update({
                "status": "FAIL",
                "blocker": "dataset_certificate_not_frozen",
                "evidence": ["dataset-freeze-certificate.json"],
            })

    certifications = {key: False for key in CERTIFICATION_KEYS}
    certifications["DATA_VERIFIED"] = _gate_pass(gate_map, "G1", "G2", "G3", "G4")
    certifications["EDGE_VERIFIED"] = certifications["DATA_VERIFIED"] and _gate_pass(
        gate_map, "G5", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "G13"
    )
    certifications["RISK_VERIFIED"] = _gate_pass(gate_map, "G14")
    certifications["EXECUTION_VERIFIED"] = _gate_pass(gate_map, "G15", "G16", "G17", "G18")
    certifications["RECONCILIATION_VERIFIED"] = _gate_pass(gate_map, "G19", "G32")
    certifications["SECURITY_VERIFIED"] = _gate_pass(gate_map, "G20", "G21", "G22")
    certifications["PRODUCTION_INFRASTRUCTURE_VERIFIED"] = _gate_pass(
        gate_map, "G23", "G24", "G25", "G26"
    )
    certifications["TESTNET_VERIFIED"] = _gate_pass(gate_map, "G28")
    certifications["SHADOW_VERIFIED"] = _gate_pass(gate_map, "G29")
    certifications["LIVE_PILOT_VERIFIED"] = _gate_pass(gate_map, "G30", "G31")
    certifications["LIVE_PRODUCTION_READY_VERIFIED"] = all((
        certifications["DATA_VERIFIED"], certifications["EDGE_VERIFIED"],
        certifications["RISK_VERIFIED"], certifications["EXECUTION_VERIFIED"],
        certifications["RECONCILIATION_VERIFIED"], certifications["SECURITY_VERIFIED"],
        certifications["PRODUCTION_INFRASTRUCTURE_VERIFIED"], certifications["TESTNET_VERIFIED"],
        certifications["SHADOW_VERIFIED"], certifications["LIVE_PILOT_VERIFIED"],
    )) and all(g["status"] == "PASS" for g in normalized)

    blockers = [
        {"gate": g["id"], "name": g["name"], "status": g["status"], "blocker": g.get("blocker")}
        for g in normalized if g["status"] != "PASS"
    ]

    decision = "LIVE_PRODUCTION_READY_VERIFIED" if certifications["LIVE_PRODUCTION_READY_VERIFIED"] else "NO_GO"
    stage = "SCALED_LIVE" if certifications["LIVE_PRODUCTION_READY_VERIFIED"] else "RESEARCH"

    ids = dict(identities or {})
    if dataset_certificate:
        ids.setdefault("dataset_sha256", dataset_certificate.get("dataset_sha256"))
        ids.setdefault("lifecycle_sha256", dataset_certificate.get("verified_lifecycle_sha256"))
        ids.setdefault("dataset_manifest_sha256", dataset_certificate.get("dataset_manifest_sha256"))
    ids.setdefault("strategy_version", None)
    ids.setdefault("strategy_config_sha256", None)
    ids.setdefault("artifact_digest", None)
    ids.setdefault("test_report_sha256", None)

    metric_defaults = {
        "oos": None, "holdout": {"opened": False, "result": None}, "dsr": None, "pbo": None,
        "white_reality_check": None, "hansen_spa": None, "cost_stress": None,
        "max_drawdown": None, "capacity": None, "risk": None, "reconciliation": None,
        "testnet": None, "shadow": None, "live_pilot": None, "security": None,
        "supply_chain": None,
    }
    metric_defaults.update(metrics or {})

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commit_sha": source_commit_sha,
        "stage": stage,
        "decision": decision,
        "live_ready": certifications["LIVE_PRODUCTION_READY_VERIFIED"],
        "certifications": certifications,
        "identities": ids,
        "metrics": metric_defaults,
        "evidence": validated,
        "gates": normalized,
        "blockers": blockers,
        "authorizations": {
            "paper": False, "testnet": False, "shadow": False,
            "live_pilot": False, "scaled_live": False,
        },
        "governance": {
            "default_deny": True,
            "probabilistic_authorization_forbidden": True,
            "human_approval_required_for_live_capital": True,
            "missing_evidence_means_no_go": True,
            "holdout_may_not_be_used_for_selection_or_tuning": True,
            "live_activation_requires_separate_human_authorization": True,
        },
        "standards": {
            "slsa": "v1.2",
            "sigstore_keyless_oidc": True,
            "github_artifact_attestations": True,
            "opentelemetry_semantic_conventions": "1.44.0",
            "nist_ai_rmf": "AI RMF 1.0 + NIST AI 600-1 where agentic/GAI components apply",
        },
    }
    return ReadinessResult(manifest, canonical_sha256(manifest))


def write_readiness(result: ReadinessResult, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "trading-production-readiness-manifest.json"
    manifest_path.write_text(json.dumps(result.manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "trading-production-readiness-manifest.sha256").write_text(
        result.canonical_sha256 + "  trading-production-readiness-manifest.json\n", encoding="utf-8"
    )
