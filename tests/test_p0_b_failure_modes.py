from __future__ import annotations

from decimal import Decimal

import pytest

from institutional_trading.binance_testnet import BrokerTimeoutUnknown, SubmittedOrder
from institutional_trading.controls import KillSwitches, RiskEngine, RiskLimits
from institutional_trading.domain import Environment, IntentState, OrderIntent
from institutional_trading.order_service import TestnetOrderService
from institutional_trading.repository import DuplicateIntentError


def make_intent(key: str = "idem-1234567890123456") -> OrderIntent:
    return OrderIntent(
        client_order_id="client-order-0001",
        idempotency_key=key,
        environment=Environment.TESTNET,
        account_ref="acct-testnet",
        strategy_id="strategy-a",
        strategy_version="1.0.0",
        symbol="BTCUSDT",
        side="BUY",
        quantity=Decimal("0.001"),
        order_type="LIMIT",
        limit_price=Decimal("10000"),
        signal_ref="signal:test",
    )


class FakeStore:
    def __init__(self) -> None:
        self.rows = {}
        self.transitions = []
        self.observations = []

    def insert_intent(self, intent):
        existing = self.rows.get(intent.idempotency_key)
        fingerprint = intent.canonical_fingerprint()
        if existing:
            if existing[1] != fingerprint:
                raise DuplicateIntentError("idempotency key reused with different intent")
            return
        self.rows[intent.idempotency_key] = (intent, fingerprint)

    def transition(self, intent_id, expected, target):
        self.transitions.append((intent_id, tuple(expected), target))
        return True

    def upsert_broker_observation(self, observation):
        self.observations.append(observation)


class AllowOPA:
    def evaluate(self, *args, **kwargs):
        class D:
            allowed = True
        return D()


class TimeoutAdapter:
    def submit(self, intent):
        raise BrokerTimeoutUnknown("simulated ambiguous timeout")


class FilledAdapter:
    def submit(self, intent):
        return SubmittedOrder("42", intent.client_order_id, "FILLED", {"orderId": 42, "status": "FILLED"})


def service(store, adapter, kill=None):
    return TestnetOrderService(
        store=store,
        opa=AllowOPA(),
        risk=RiskEngine(RiskLimits(max_notional=Decimal("1000"), max_quantity=Decimal("1"))),
        kill_switches=kill or KillSwitches(),
        adapter=adapter,
    )


def test_timeout_becomes_unknown_and_is_not_resubmitted_implicitly():
    store = FakeStore()
    state = service(store, TimeoutAdapter()).submit(make_intent(), reference_price=Decimal("10000"))
    assert state == IntentState.UNKNOWN
    assert store.transitions[-1][2] == IntentState.UNKNOWN


def test_global_kill_switch_blocks_before_adapter_submission():
    store = FakeStore()
    kill = KillSwitches()
    kill.engage_global()
    state = service(store, FilledAdapter(), kill).submit(make_intent(), reference_price=Decimal("10000"))
    assert state == IntentState.SUSPENDED
    assert not store.observations


def test_idempotency_key_cannot_identify_different_order():
    store = FakeStore()
    first = make_intent()
    store.insert_intent(first)
    conflicting = first.model_copy(update={"symbol": "ETHUSDT"})
    with pytest.raises(DuplicateIntentError):
        store.insert_intent(conflicting)


def test_crash_recovery_invariant_persists_intent_before_submission():
    store = FakeStore()
    intent = make_intent()
    state = service(store, TimeoutAdapter()).submit(intent, reference_price=Decimal("10000"))
    assert intent.idempotency_key in store.rows
    assert state == IntentState.UNKNOWN


def test_successful_testnet_fill_reaches_terminal_state():
    store = FakeStore()
    state = service(store, FilledAdapter()).submit(make_intent(), reference_price=Decimal("10000"))
    assert state == IntentState.FILLED
    assert store.observations[0].broker_order_id == "42"
