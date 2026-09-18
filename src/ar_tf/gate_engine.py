from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

@dataclass(frozen=True)
class GateResult:
    gate_id: str
    passed: bool
    evidence_sha256: str
    details: Mapping[str, Any]

MANDATORY_GATES = (
    "DATA_INTEGRITY","POINT_IN_TIME","NO_LEAKAGE","REPRODUCIBILITY",
    "NET_OOS","COST_STRESS","MULTIPLE_TESTING","PARAMETER_STABILITY",
    "REGIME_STABILITY","LIQUIDITY_CAPACITY","EXECUTION_REALISM","EVIDENCE_INTEGRITY",
)

def adjudicate(results: Iterable[GateResult], *, holdout_opened: bool=False) -> dict[str, Any]:
    if holdout_opened: raise ValueError("holdout must remain closed during selection")
    rows=list(results)
    ids=[r.gate_id for r in rows]
    if len(ids)!=len(set(ids)): raise ValueError("duplicate gate result")
    by_id={r.gate_id:r for r in rows}
    missing=[g for g in MANDATORY_GATES if g not in by_id]
    if missing: raise ValueError(f"missing mandatory gates: {missing}")
    for r in rows:
        if len(r.evidence_sha256)!=64: raise ValueError(f"invalid evidence digest: {r.gate_id}")
    failed=[g for g in MANDATORY_GATES if not by_id[g].passed]
    decision="FROZEN_HOLDOUT_CANDIDATE" if not failed else "NO_EDGE_VERIFIED"
    return {
        "decision":decision,"all_mandatory_passed":not failed,"failed_gates":failed,
        "holdout_opened":False,"paper_authorized":False,"testnet_authorized":False,"live_authorized":False,
    }
