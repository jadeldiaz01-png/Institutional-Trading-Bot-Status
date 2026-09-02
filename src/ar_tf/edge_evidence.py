from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Iterable


class EvidenceClass(str, Enum):
    EXTERNAL_PRIOR = "EXTERNAL_PRIOR"
    INTERNAL_RESEARCH = "INTERNAL_RESEARCH"
    INTERNAL_OOS = "INTERNAL_OOS"
    FINAL_HOLDOUT = "FINAL_HOLDOUT"
    FORWARD_PAPER = "FORWARD_PAPER"
    TESTNET_EXECUTION = "TESTNET_EXECUTION"
    LIVE_PILOT = "LIVE_PILOT"


@dataclass(frozen=True)
class EdgeEvidence:
    evidence_id: str
    evidence_class: EvidenceClass
    reproducible: bool
    point_in_time: bool
    net_of_costs: bool
    multiplicity_adjusted: bool
    holdout_untouched: bool
    execution_realism: bool
    positive_expectancy: bool
    notes: str = ""


@dataclass(frozen=True)
class EdgeGatePolicy:
    min_dsr_probability: float = 0.95
    max_pbo: float = 0.20
    require_spa_or_reality_check: bool = True
    require_parameter_plateau: bool = True
    require_regime_stability: bool = True
    require_cost_stress_survival: bool = True
    require_benchmark_superiority: bool = True


def classify_public_result(*, source_id: str, notes: str = "") -> EdgeEvidence:
    """Public papers/platform results are priors, never proof for AR-TF."""
    return EdgeEvidence(
        evidence_id=source_id,
        evidence_class=EvidenceClass.EXTERNAL_PRIOR,
        reproducible=False,
        point_in_time=False,
        net_of_costs=False,
        multiplicity_adjusted=False,
        holdout_untouched=True,
        execution_realism=False,
        positive_expectancy=False,
        notes=notes,
    )


def pre_holdout_edge_decision(
    evidence: Iterable[EdgeEvidence],
    *,
    dataset_frozen: bool,
    dataset_sha256: str | None,
    lifecycle_sha256: str | None,
    unresolved_data_defects: int,
    all_trials_preregistered: bool,
    common_oos_folds: bool,
    dsr_probability: float | None,
    pbo: float | None,
    spa_or_reality_check_passed: bool,
    parameter_plateau_passed: bool,
    regime_stability_passed: bool,
    cost_stress_passed: bool,
    benchmark_superiority_passed: bool,
) -> dict:
    """Fail-closed research gate. It can never authorize PAPER or LIVE."""
    reasons: list[str] = []
    if not dataset_frozen or not dataset_sha256 or not lifecycle_sha256:
        reasons.append("DATASET_NOT_CRYPTOGRAPHICALLY_FROZEN")
    if unresolved_data_defects != 0:
        reasons.append("UNRESOLVED_DATA_DEFECTS")
    if not all_trials_preregistered:
        reasons.append("TRIALS_NOT_PREREGISTERED")
    if not common_oos_folds:
        reasons.append("NON_COMMON_OOS_FOLDS")
    if dsr_probability is None or dsr_probability < 0.95:
        reasons.append("DSR_GATE_FAILED")
    if pbo is None or pbo > 0.20:
        reasons.append("PBO_GATE_FAILED")
    if not spa_or_reality_check_passed:
        reasons.append("MULTIPLE_TESTING_BENCHMARK_GATE_FAILED")
    if not parameter_plateau_passed:
        reasons.append("PARAMETER_PLATEAU_GATE_FAILED")
    if not regime_stability_passed:
        reasons.append("REGIME_STABILITY_GATE_FAILED")
    if not cost_stress_passed:
        reasons.append("COST_STRESS_GATE_FAILED")
    if not benchmark_superiority_passed:
        reasons.append("BENCHMARK_SUPERIORITY_GATE_FAILED")

    internal_positive = [
        item for item in evidence
        if item.evidence_class in {EvidenceClass.INTERNAL_OOS, EvidenceClass.INTERNAL_RESEARCH}
        and item.reproducible
        and item.point_in_time
        and item.net_of_costs
        and item.multiplicity_adjusted
        and item.positive_expectancy
    ]
    if not internal_positive:
        reasons.append("NO_REPRODUCIBLE_NET_POSITIVE_INTERNAL_OOS_EVIDENCE")

    decision = "FROZEN_HOLDOUT_CANDIDATE" if not reasons else "NO_EDGE_VERIFIED"
    return {
        "decision": decision,
        "paper_authorized": False,
        "testnet_authorized": False,
        "live_authorized": False,
        "holdout_evaluated": False,
        "reasons": reasons,
        "evidence": [asdict(x) for x in evidence],
        "required_next_gate": (
            "SINGLE_UNTOUCHED_365D_HOLDOUT"
            if decision == "FROZEN_HOLDOUT_CANDIDATE"
            else "REMEDIATE_FAILED_RESEARCH_GATES"
        ),
    }
