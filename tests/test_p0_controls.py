from decimal import Decimal

import pytest

from institutional_trading.controls import ControlUnavailable, KillSwitches, PolicyEngine, RiskEngine, RiskLimits
from institutional_trading.domain import Environment, IntentState, OrderIntent
from institutional_trading.evidence import EvidenceEvent
from institutional_trading.reconciliation import BrokerObservation, Reconciler


def intent(environment: Environment = Environment.TESTNET, approval_ref: str | None = None) -> OrderIntent:
    return OrderIntent(
        client_order_id="client-00000001",
        idempotency_key="idem-00000000000001",
        environment=environment,
        account_ref="acct-1",
        strategy_id="strategy-1",
        strategy_version="1.0.0",
        symbol="BTCUSDT",
        side="BUY",
        quantity=Decimal("0.001"),
        order_type="MARKET",
        signal_ref="signal:1",
        approval_ref=approval_ref,
    )


def test_prod_requires_explicit_approval() -> None:
    with pytest.raises(ValueError):
        intent(Environment.PROD)


def test_prod_is_denied_when_live_flag_is_false() -> None:
    decision = PolicyEngine().evaluate(intent(Environment.PROD, "approval:dual:1"), live_trading_enabled=False)
    assert decision.allowed is False


def test_risk_engine_unavailable_fails_closed() -> None:
    with pytest.raises(ControlUnavailable):
        RiskEngine(None).evaluate(intent(), reference_price=Decimal("50000"))


def test_kill_switch_blocks_strategy() -> None:
    switches = KillSwitches()
    order = intent()
    switches.engage_strategy(order.strategy_id)
    with pytest.raises(ControlUnavailable):
        switches.assert_clear(order)


def test_unknown_stays_unknown_without_broker_evidence() -> None:
    result = Reconciler().resolve(IntentState.UNKNOWN, BrokerObservation(found=False, status=None))
    assert result == IntentState.UNKNOWN


def test_unknown_resolves_only_from_observation() -> None:
    result = Reconciler().resolve(IntentState.UNKNOWN, BrokerObservation(found=True, status="FILLED"))
    assert result == IntentState.FILLED


def test_evidence_event_detects_tampering() -> None:
    sealed = EvidenceEvent(actor="risk-engine", event_type="RISK_DECISION", subject_ref="intent:1", payload={"allowed": False}).seal()
    assert sealed.verify() is True
    tampered = sealed.model_copy(update={"payload": {"allowed": True}})
    assert tampered.verify() is False


def test_hard_notional_limit() -> None:
    engine = RiskEngine(RiskLimits(max_notional=Decimal("10"), max_quantity=Decimal("1")))
    decision = engine.evaluate(intent(), reference_price=Decimal("50000"))
    assert decision.allowed is False
