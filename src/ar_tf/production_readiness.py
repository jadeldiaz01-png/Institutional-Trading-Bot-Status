from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .evidence_validation import validate_domain_evidence

SCHEMA_VERSION = "2026-09-10"
STAGES = ("RESEARCH", "VERIFIED_BACKTEST", "PAPER", "TESTNET", "SHADOW", "LIVE_PILOT", "SCALED_LIVE")
REQUIRED_DOMAINS = (
    "repository", "dataset", "quantitative", "execution", "risk", "reconciliation",
    "security", "secrets_identity", "supply_chain", "cicd", "observability",
    "reliability", "backup_restore", "governance", "finops",
)
SCOPE_FIELDS = ("strategy_id", "asset_class", "venue", "market", "timeframe", "dataset_id", "environment")
GATE_NAMES = {
    "G0": "Repository Integrity", "G1": "Data Integrity", "G2": "Point-in-Time Universe", "G3": "Dataset Freeze",
    "G4": "Bias Audit", "G5": "Strategy Preregistration", "G6": "Backtest Correctness", "G7": "OOS Validation",
    "G8": "Statistical Validation", "G9": "Cost Stress", "G10": "Robustness", "G11": "Regime Analysis",
    "G12": "Liquidity/Capacity", "G13": "Portfolio Construction", "G14": "Risk Engine", "G15": "Order Lifecycle",
    "G16": "OMS/EMS", "G17": "Exchange Adapter", "G18": "Idempotency", "G19": "Reconciliation",
    "G20": "Security", "G21": "Secrets/Identity", "G22": "Supply Chain", "G23": "CI/CD", "G24": "Observability",
    "G25": "Resilience", "G26": "Backup/Restore", "G27": "PAPER", "G28": "TESTNET", "G29": "SHADOW",
    "G30": "LIVE_PILOT", "G31": "Forward Evidence", "G32": "Production Reconciliation",
}
GATE_IDS = tuple(GATE_NAMES)
CERTIFICATION_KEYS = (
    "DATA_VERIFIED", "EDGE_VERIFIED", "EXECUTION_VERIFIED", "RISK_VERIFIED", "RECONCILIATION_VERIFIED",
    "SECURITY_VERIFIED", "PRODUCTION_INFRASTRUCTURE_VERIFIED", "TESTNET_VERIFIED", "SHADOW_VERIFIED",
    "LIVE_PILOT_VERIFIED", "LIVE_PRODUCTION_READY_VERIFIED",
)


@dataclass(frozen=True)
class ReadinessResult:
    manifest: dict[str, Any]
    canonical_sha256: str


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _normalize_scope(scope: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(scope or {})
    payload = {field: str(raw.get(field) or "UNBOUND") for field in SCOPE_FIELDS}
    bound = all(payload[field] != "UNBOUND" for field in SCOPE_FIELDS)
    return {**payload, "bound": bound, "scope_sha256": canonical_sha256(payload)}


def _domain(status: str = "MISSING", items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"status": status, "items": items or [], "validation_reasons": []}


def _default_gate(gate_id: str) -> dict[str, Any]:
    return {"id": gate_id, "name": GATE_NAMES[gate_id], "status": "BLOCKED", "blocking": True, "evidence": [], "blocker": "missing_verifiable_evidence"}


def _dataset_item(c: dict[str, Any], evaluation_commit_sha: str, scope: dict[str, Any]) -> dict[str, Any]:
    producer_commit = str(c.get("code_sha") or c.get("source_code_sha") or "")
    certificate_sha = str(c.get("certificate_file_sha256") or c.get("dataset_freeze_certificate_file_sha256") or "")
    external = producer_commit != evaluation_commit_sha
    item: dict[str, Any] = {
        "status": "PASS",
        "artifact": "dataset-freeze-certificate.json",
        "sha256": certificate_sha,
        "source_commit_sha": producer_commit,
        "issuer": "ar-tf-v1d2-data",
        "verification": "VERIFIED",
        "scope_sha256": scope["scope_sha256"],
        "evidence_class": "EXTERNAL_IMMUTABLE" if external else "SAME_COMMIT",
        "subject_digests": {
            "dataset_sha256": c.get("dataset_sha256"),
            "dataset_manifest_sha256": c.get("dataset_manifest_sha256"),
            "verified_lifecycle_sha256": c.get("verified_lifecycle_sha256"),
        },
        "provenance": {"required": False, "verified": False},
    }
    if external:
        item["cross_commit_binding"] = {
            "consumer_commit_sha": evaluation_commit_sha,
            "source_artifact_digest": c.get("source_artifact_digest"),
            "source_artifact_id": c.get("source_artifact_id"),
            "source_run_id": c.get("source_run_id"),
            "verification_method": "GITHUB_ACTIONS_ARTIFACT_DIGEST_AND_CONTENT_HASH",
            "verified": c.get("external_verification") is True,
        }
    return item


def _dataset_is_frozen(c: dict[str, Any], scope: dict[str, Any]) -> bool:
    artifact_digest = str(c.get("source_artifact_digest") or "")
    producer_commit = str(c.get("code_sha") or c.get("source_code_sha") or "")
    certificate_sha = str(c.get("certificate_file_sha256") or c.get("dataset_freeze_certificate_file_sha256") or "")
    return bool(
        scope.get("bound") is True
        and c.get("dataset_id") == scope.get("dataset_id")
        and c.get("decision") == "FROZEN_DATASET"
        and c.get("frozen") is True
        and c.get("unresolved_count") == 0
        and c.get("unresolved_anomaly_count") == 0
        and c.get("unresolved_gap_count") == 0
        and c.get("invalid_checksum_evidence_count") == 0
        and c.get("lifecycle_binding_verified") is True
        and c.get("source_plan_binding_verified") is True
        and c.get("holdout_evaluated") is False
        and c.get("external_verification") is True
        and isinstance(c.get("dataset_sha256"), str) and len(c["dataset_sha256"]) == 64
        and len(producer_commit) == 40
        and len(certificate_sha) == 64
        and artifact_digest.startswith("sha256:") and len(artifact_digest) == 71
        and bool(c.get("source_artifact_id"))
        and bool(c.get("source_run_id"))
    )


def _normalize_gates(gates: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    supplied = {str(g.get("id")): dict(g) for g in (gates or []) if g.get("id") in GATE_NAMES}
    out = []
    for gid in GATE_IDS:
        gate = _default_gate(gid)
        if gid in supplied:
            gate.update(supplied[gid]); gate["name"] = GATE_NAMES[gid]; gate.setdefault("evidence", [])
            if gate.get("status") not in {"PASS", "FAIL", "BLOCKED"}:
                gate.update({"status": "FAIL", "blocker": "invalid_gate_status"})
        out.append(gate)
    return out


def _gate_pass(gates: dict[str, dict[str, Any]], *ids: str) -> bool:
    return all(gates[i]["status"] == "PASS" for i in ids)


def _domain_pass(evidence: dict[str, dict[str, Any]], *names: str) -> bool:
    return all(evidence[n]["status"] in {"PASS", "NOT_APPLICABLE"} for n in names)


def evaluate_readiness(
    *, source_commit_sha: str, scope: dict[str, Any] | None = None,
    dataset_certificate: dict[str, Any] | None = None, evidence: dict[str, dict[str, Any]] | None = None,
    gates: list[dict[str, Any]] | None = None, identities: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> ReadinessResult:
    """Deterministic, fail-closed readiness semantics over an explicitly bound scope.

    The final file contains a generation timestamp, so a separate semantic snapshot hash
    excludes only that timestamp and is reproducible for an otherwise identical evidence set.
    No gate, model output, signature, or self-declared PASS authorizes capital by itself.
    """
    if len(source_commit_sha) != 40 or any(c not in "0123456789abcdef" for c in source_commit_sha):
        raise ValueError("source_commit_sha must be a lowercase 40-hex Git SHA")

    normalized_scope = _normalize_scope(scope)
    evidence = {k: dict(v) for k, v in (evidence or {}).items()}
    for name in REQUIRED_DOMAINS: evidence.setdefault(name, _domain())

    dataset_ok = False
    if dataset_certificate is not None:
        dataset_ok = _dataset_is_frozen(dataset_certificate, normalized_scope)
        evidence["dataset"] = _domain(
            "PASS" if dataset_ok else "FAIL",
            [_dataset_item(dataset_certificate, source_commit_sha, normalized_scope)] if dataset_ok else [],
        )

    validated: dict[str, dict[str, Any]] = {}
    for name in REQUIRED_DOMAINS:
        domain = dict(evidence[name]); domain.setdefault("items", []); domain.setdefault("validation_reasons", [])
        if domain.get("status") == "PASS":
            ok, reasons = validate_domain_evidence(
                domain,
                expected_commit_sha=source_commit_sha,
                expected_scope_sha256=normalized_scope["scope_sha256"],
            )
            domain["validation_reasons"] = reasons
            if not ok: domain["status"] = "FAIL"
        elif domain.get("status") not in {"FAIL", "MISSING", "NOT_APPLICABLE"}:
            domain.update({"status": "FAIL", "validation_reasons": ["invalid_domain_status"]})
        validated[name] = domain

    normalized = _normalize_gates(gates); gate_map = {g["id"]: g for g in normalized}
    if dataset_ok and validated["dataset"]["status"] == "PASS":
        for gid in ("G1", "G3"): gate_map[gid].update({"status": "PASS", "blocker": None, "evidence": ["dataset-freeze-certificate.json"]})
    elif dataset_certificate is not None:
        for gid in ("G1", "G3"): gate_map[gid].update({"status": "FAIL", "blocker": "dataset_certificate_or_scope_not_verified", "evidence": ["dataset-freeze-certificate.json"]})

    c = {key: False for key in CERTIFICATION_KEYS}
    scope_bound = normalized_scope["bound"] is True
    c["DATA_VERIFIED"] = scope_bound and _domain_pass(validated, "dataset") and _gate_pass(gate_map, "G1", "G2", "G3", "G4")
    c["EDGE_VERIFIED"] = c["DATA_VERIFIED"] and _domain_pass(validated, "quantitative") and _gate_pass(gate_map, "G5", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "G13")
    c["RISK_VERIFIED"] = scope_bound and _domain_pass(validated, "risk") and _gate_pass(gate_map, "G14")
    c["EXECUTION_VERIFIED"] = scope_bound and _domain_pass(validated, "execution") and _gate_pass(gate_map, "G15", "G16", "G17", "G18")
    c["RECONCILIATION_VERIFIED"] = scope_bound and _domain_pass(validated, "reconciliation") and _gate_pass(gate_map, "G19", "G32")
    c["SECURITY_VERIFIED"] = scope_bound and _domain_pass(validated, "security", "secrets_identity", "supply_chain") and _gate_pass(gate_map, "G20", "G21", "G22")
    c["PRODUCTION_INFRASTRUCTURE_VERIFIED"] = scope_bound and _domain_pass(validated, "repository", "cicd", "observability", "reliability", "backup_restore", "governance", "finops") and _gate_pass(gate_map, "G0", "G23", "G24", "G25", "G26")
    c["TESTNET_VERIFIED"] = scope_bound and _domain_pass(validated, "execution", "risk", "reconciliation", "observability") and _gate_pass(gate_map, "G28")
    c["SHADOW_VERIFIED"] = scope_bound and _domain_pass(validated, "quantitative", "execution", "observability") and _gate_pass(gate_map, "G29")
    c["LIVE_PILOT_VERIFIED"] = scope_bound and _domain_pass(validated, "execution", "risk", "reconciliation", "observability") and _gate_pass(gate_map, "G30", "G31")
    c["LIVE_PRODUCTION_READY_VERIFIED"] = scope_bound and all((c["DATA_VERIFIED"], c["EDGE_VERIFIED"], c["RISK_VERIFIED"], c["EXECUTION_VERIFIED"], c["RECONCILIATION_VERIFIED"], c["SECURITY_VERIFIED"], c["PRODUCTION_INFRASTRUCTURE_VERIFIED"], c["TESTNET_VERIFIED"], c["SHADOW_VERIFIED"], c["LIVE_PILOT_VERIFIED"])) and _gate_pass(gate_map, "G27") and all(g["status"] == "PASS" for g in normalized)

    blockers = [{"gate": g["id"], "name": g["name"], "status": g["status"], "blocker": g.get("blocker")} for g in normalized if g["status"] != "PASS"]
    decision = "LIVE_PRODUCTION_READY_VERIFIED" if c["LIVE_PRODUCTION_READY_VERIFIED"] else "NO_GO"
    if c["LIVE_PRODUCTION_READY_VERIFIED"]: stage = "SCALED_LIVE"
    elif c["LIVE_PILOT_VERIFIED"]: stage = "LIVE_PILOT"
    elif c["SHADOW_VERIFIED"]: stage = "SHADOW"
    elif c["TESTNET_VERIFIED"]: stage = "TESTNET"
    elif c["EDGE_VERIFIED"] and c["RISK_VERIFIED"] and _gate_pass(gate_map, "G27"): stage = "PAPER"
    elif c["EDGE_VERIFIED"]: stage = "VERIFIED_BACKTEST"
    else: stage = "RESEARCH"

    ids = dict(identities or {})
    if dataset_certificate:
        ids.setdefault("dataset_sha256", dataset_certificate.get("dataset_sha256")); ids.setdefault("lifecycle_sha256", dataset_certificate.get("verified_lifecycle_sha256")); ids.setdefault("dataset_manifest_sha256", dataset_certificate.get("dataset_manifest_sha256")); ids.setdefault("dataset_producer_commit_sha", dataset_certificate.get("code_sha") or dataset_certificate.get("source_code_sha"))
    for key in ("strategy_version", "strategy_config_sha256", "artifact_digest", "test_report_sha256"): ids.setdefault(key, None)

    metric_defaults = {"oos": None, "holdout": {"opened": False, "result": None}, "dsr": None, "pbo": None, "white_reality_check": None, "hansen_spa": None, "cost_stress": None, "max_drawdown": None, "capacity": None, "risk": None, "reconciliation": None, "testnet": None, "shadow": None, "live_pilot": None, "security": None, "supply_chain": None}
    metric_defaults.update(metrics or {})

    manifest = {
        "schema_version": SCHEMA_VERSION, "generated_at": datetime.now(timezone.utc).isoformat(), "commit_sha": source_commit_sha,
        "scope": normalized_scope, "stage": stage, "decision": decision, "live_ready": c["LIVE_PRODUCTION_READY_VERIFIED"], "certifications": c,
        "identities": ids, "metrics": metric_defaults, "evidence": validated, "gates": normalized, "blockers": blockers,
        "authorizations": {"paper": False, "testnet": False, "shadow": False, "live_pilot": False, "scaled_live": False},
        "governance": {"default_deny": True, "probabilistic_authorization_forbidden": True, "human_approval_required_for_live_capital": True, "missing_evidence_means_no_go": True, "holdout_may_not_be_used_for_selection_or_tuning": True, "live_activation_requires_separate_human_authorization": True, "cross_scope_evidence_forbidden": True},
        "standards": {"slsa": "v1.2", "sigstore_keyless_oidc": True, "github_artifact_attestations": True, "opentelemetry_semantic_conventions": "1.44.0", "nist_ai_rmf": "AI RMF 1.0 + NIST AI 600-1 where agentic/GAI components apply", "owasp_agent_control_standard": "2026-09-01", "owasp_agentic_top10": "2026"},
    }
    semantic_payload = {k: v for k, v in manifest.items() if k != "generated_at"}
    manifest["semantic_snapshot_sha256"] = canonical_sha256(semantic_payload)
    return ReadinessResult(manifest, canonical_sha256(manifest))


def write_readiness(result: ReadinessResult, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "trading-production-readiness-manifest.json"
    path.write_text(json.dumps(result.manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "trading-production-readiness-manifest.sha256").write_text(result.canonical_sha256 + "  trading-production-readiness-manifest.json\n", encoding="utf-8")
