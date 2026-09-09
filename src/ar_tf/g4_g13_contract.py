from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

GATES = ("G4", "G5", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "G13")
VALID_STATUSES = {"PASS", "FAIL", "BLOCKED"}


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def evaluate_g4_g13(
    *,
    bias_audit: dict[str, Any],
    preregistration: dict[str, Any],
    tournament: dict[str, Any] | None,
) -> dict[str, Any]:
    gates = {g: {"status": "BLOCKED", "reasons": ["MISSING_VERIFIABLE_EVIDENCE"]} for g in GATES}

    if bias_audit.get("decision") == "PASS" and bias_audit.get("holdout_values_evaluated") is False and bias_audit.get("holdout_opened") is False:
        gates["G4"] = {"status": "PASS", "reasons": []}
    else:
        gates["G4"] = {"status": "FAIL", "reasons": list(bias_audit.get("reasons", [])) or ["BIAS_AUDIT_FAILED"]}

    p = preregistration
    g5_ok = (
        p.get("decision") == "PASS"
        and p.get("state") == "PREREGISTERED_NOT_EXECUTED"
        and p.get("trial_count") == 407
        and p.get("holdout_evaluated") is False
        and all(isinstance(p.get(k), str) and len(p[k]) == n for k, n in (
            ("source_commit_sha", 40), ("dataset_sha256", 64), ("lifecycle_sha256", 64),
            ("strategy_config_sha256", 64), ("fold_definition_sha256", 64), ("trial_registry_sha256", 64),
        ))
    )
    gates["G5"] = {"status": "PASS" if g5_ok else "FAIL", "reasons": [] if g5_ok else ["PREREGISTRATION_BINDING_FAILED"]}

    if tournament is not None:
        if tournament.get("holdout_evaluated") is not False or tournament.get("holdout_opened") is not False:
            for gid in GATES[2:]:
                gates[gid] = {"status": "FAIL", "reasons": ["HOLDOUT_CONTAMINATION"]}
        else:
            supplied = tournament.get("gate_results", {})
            for gid in GATES[2:]:
                item = supplied.get(gid)
                if not isinstance(item, dict):
                    gates[gid] = {"status": "BLOCKED", "reasons": ["MISSING_EXPLICIT_GATE_RESULT"]}
                    continue
                status = item.get("status")
                reasons = list(item.get("reasons", []))
                if status not in VALID_STATUSES:
                    gates[gid] = {"status": "FAIL", "reasons": ["INVALID_GATE_STATUS"]}
                    continue
                gates[gid] = {"status": status, "reasons": reasons}

    all_pass = all(gates[g]["status"] == "PASS" for g in GATES)
    result = {
        "schema_version": "1.1.0",
        "scope": "G4-G13_PRE_HOLDOUT",
        "gates": gates,
        "all_g4_g13_pass": all_pass,
        "holdout_opened": False,
        "holdout_evaluated": False,
        "paper_authorized": False,
        "testnet_authorized": False,
        "live_authorized": False,
        "decision": "PRE_HOLDOUT_GATES_PASS" if all_pass else "NO_EDGE_VERIFIED",
    }
    result["certificate_sha256"] = canonical_sha256(result)
    return result


def write_certificate(value: dict[str, Any], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
