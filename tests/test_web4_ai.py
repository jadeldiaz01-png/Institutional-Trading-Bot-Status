import pytest

from ar_tf.web4_ai import (
    Web4Component,
    admission_decision,
    authorize_capability,
    registry_report,
    score_component,
)


def test_trading_authority_is_always_denied():
    for capability in [
        "place_order", "cancel_order", "change_risk_limit", "open_holdout",
        "promote_strategy", "enable_live_trading", "move_capital",
    ]:
        assert authorize_capability(capability, live_trading_enabled=False) is False
        assert authorize_capability(capability, live_trading_enabled=True) is False


def test_research_capabilities_are_allowlisted():
    assert authorize_capability("retrieve_evidence") is True
    assert authorize_capability("run_sandbox_evaluation") is True
    assert authorize_capability("unknown_capability") is False


def test_experimental_component_cannot_be_admitted_automatically():
    x = Web4Component("kg", "KG-RAG", 5, 5, 5, 5, 5, experimental=True)
    report = admission_decision(x)
    assert report["score"] == 100.0
    assert report["decision"] == "RESEARCH_ONLY"


def test_low_score_fails_closed():
    x = Web4Component("weak", "experimental", 1, 1, 1, 1, 1)
    assert admission_decision(x)["decision"] == "NO_GO"


def test_score_bounds_are_enforced():
    with pytest.raises(ValueError):
        score_component(Web4Component("bad", "x", 6, 1, 1, 1, 1))


def test_default_registry_contains_no_profitability_or_execution_authority():
    report = registry_report()
    assert any(x["component_id"] == "mcp_tools" for x in report)
    assert all(x["decision"] in {"ADVISORY_ADMITTED", "RESEARCH_ONLY", "NO_GO"} for x in report)
