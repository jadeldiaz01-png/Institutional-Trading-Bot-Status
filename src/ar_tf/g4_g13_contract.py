from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

GATES = ("G4", "G5", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "G13")

REQUIRED_G6_G13_EVIDENCE = {
    "G6": ("backtest_correctness", "one_bar_execution_delay", "point_in_time_features", "failed_trials_retained"),
    "G7": ("common_oos_folds", "purged", "embargoed", "oos_return_matrix_sha256"),
    "G8": ("dsr", "pbo", "white_reality_check", "hansen_spa", "block_bootstrap"),
    "G9": ("base_costs", "stressed_costs", "severe_costs", "binance_filter_model"),
    "G10": ("parameter_plateau", "entry_delay", "execution_delay", "random_slippage", "missing_trade_stress"),
    "G11": ("calendar_year", "bull_bear_sideways", "volatility", "liquidity", "dispersion"),
    "G12": ("turnover", "liquidity", "capacity", "market_impact"),
    "G13": ("position_sizing", "concentration", "gross_exposure", "volatility_target", "portfolio_risk"),
}


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
            evidence = tournament.get("evidence", {})
            for gid, required in REQUIRED_G6_G13_EVIDENCE.items():
                missing = [key for key in required if not evidence.get(key)]
                gates[gid] = {"status": "PASS" if not missing else "BLOCKED", "reasons": [f"MISSING:{x}" for x in missing]}

    all_pass = all(gates[g]["status"] == "PASS" for g in GATES)
    result = {
        "schema_version": "1.0.0",
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
