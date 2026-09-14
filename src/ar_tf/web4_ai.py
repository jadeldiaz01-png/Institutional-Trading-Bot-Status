from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable


FORBIDDEN_CAPABILITIES = {
    "place_order",
    "cancel_order",
    "change_risk_limit",
    "open_holdout",
    "promote_strategy",
    "enable_live_trading",
    "move_capital",
    "write_exchange_credentials",
}

ALLOWED_RESEARCH_CAPABILITIES = {
    "read_research_data",
    "read_public_market_data",
    "retrieve_evidence",
    "query_knowledge_graph",
    "summarize_research",
    "propose_hypothesis",
    "run_sandbox_evaluation",
    "emit_signed_evidence",
}


@dataclass(frozen=True)
class Web4Component:
    component_id: str
    protocol: str
    maturity: float
    security: float
    evidence_quality: float
    trading_relevance: float
    operational_simplicity: float
    experimental: bool = False


def score_component(component: Web4Component) -> float:
    """Weighted 0-100 research-admission score.

    Security/evidence/relevance dominate hype and novelty. Operational simplicity
    is rewarded because every additional distributed component increases failure
    modes in a trading control plane.
    """
    values = {
        "maturity": component.maturity,
        "security": component.security,
        "evidence_quality": component.evidence_quality,
        "trading_relevance": component.trading_relevance,
        "operational_simplicity": component.operational_simplicity,
    }
    if any(not 0.0 <= v <= 5.0 for v in values.values()):
        raise ValueError("component scores must be in [0, 5]")
    weighted = (
        0.20 * component.maturity
        + 0.25 * component.security
        + 0.20 * component.evidence_quality
        + 0.25 * component.trading_relevance
        + 0.10 * component.operational_simplicity
    )
    return round(weighted / 5.0 * 100.0, 2)


def admission_decision(component: Web4Component, minimum_score: float = 70.0) -> dict:
    score = score_component(component)
    if component.experimental:
        state = "RESEARCH_ONLY"
    elif score >= minimum_score:
        state = "ADVISORY_ADMITTED"
    else:
        state = "NO_GO"
    return {**asdict(component), "score": score, "decision": state}


def authorize_capability(capability: str, *, live_trading_enabled: bool = False) -> bool:
    """AI/Web4 capabilities are research-only and fail closed.

    Even if live trading is enabled elsewhere in the system, this layer never
    receives trading authority. Execution remains behind deterministic Risk,
    Policy, OMS and human-approval gates.
    """
    if capability in FORBIDDEN_CAPABILITIES:
        return False
    if live_trading_enabled:
        # No privilege expansion is granted merely because another subsystem is live.
        return capability in ALLOWED_RESEARCH_CAPABILITIES
    return capability in ALLOWED_RESEARCH_CAPABILITIES


def default_component_registry() -> list[Web4Component]:
    """2026 evidence-weighted hypotheses; scores are governance priors, not alpha claims."""
    return [
        Web4Component("mcp_tools", "MCP-2026-07-28", 5.0, 4.5, 5.0, 4.5, 4.5),
        Web4Component("a2a_agents", "A2A-v1.0", 4.5, 4.0, 4.5, 3.5, 3.5),
        Web4Component("kg_rag", "KG-RAG", 3.5, 4.0, 3.5, 3.5, 3.0, experimental=True),
        Web4Component("agent_identity", "W3C-DID-1.1+VC", 3.5, 3.5, 3.5, 2.5, 2.5, experimental=True),
        Web4Component("confidential_ai", "TEE-attestation", 3.5, 4.5, 3.5, 2.5, 2.0, experimental=True),
    ]


def registry_report(components: Iterable[Web4Component] | None = None) -> list[dict]:
    return [admission_decision(x) for x in (components or default_component_registry())]
