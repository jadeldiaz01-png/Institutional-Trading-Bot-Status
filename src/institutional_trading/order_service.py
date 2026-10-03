from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .binance_testnet import BinanceSpotTestnetAdapter, BrokerRejected, BrokerTimeoutUnknown
from .controls import ControlUnavailable, KillSwitches, RiskEngine
from .domain import Environment, IntentState, OrderIntent
from .opa_client import OPAClient
from .repository import BrokerObservation, PostgresStore
from datetime import datetime, timezone


@dataclass(slots=True)
class TestnetOrderService:
    store: PostgresStore
    opa: OPAClient
    risk: RiskEngine
    kill_switches: KillSwitches
    adapter: BinanceSpotTestnetAdapter

    def submit(self, intent: OrderIntent, *, reference_price: Decimal,
               workload_verified: bool = True) -> IntentState:
        if intent.environment != Environment.TESTNET:
            raise ValueError("P0-B service is TESTNET-only")

        # Persist first. A process crash after this point is recoverable by reconciliation.
        self.store.insert_intent(intent)

        try:
            self.kill_switches.assert_clear(intent)
        except ControlUnavailable:
            self.store.transition(intent.intent_id, [IntentState.CREATED], IntentState.SUSPENDED)
            return IntentState.SUSPENDED

        risk_decision = self.risk.evaluate(intent, reference_price=reference_price)
        if not risk_decision.allowed:
            self.store.transition(intent.intent_id, [IntentState.CREATED], IntentState.REJECTED)
            return IntentState.REJECTED

        policy_decision = self.opa.evaluate(
            intent,
            risk_allowed=True,
            kill_switch_clear=True,
            workload_verified=workload_verified,
            audit_available=True,
            reconciliation_available=True,
            live_trading_enabled=False,
        )
        if not policy_decision.allowed:
            self.store.transition(intent.intent_id, [IntentState.CREATED], IntentState.REJECTED)
            return IntentState.REJECTED

        self.store.transition(intent.intent_id, [IntentState.CREATED], IntentState.RISK_APPROVED)
        self.store.transition(intent.intent_id, [IntentState.RISK_APPROVED], IntentState.SUBMITTING)

        try:
            submitted = self.adapter.submit(intent)
        except BrokerTimeoutUnknown:
            self.store.transition(intent.intent_id, [IntentState.SUBMITTING], IntentState.UNKNOWN)
            return IntentState.UNKNOWN
        except BrokerRejected:
            self.store.transition(intent.intent_id, [IntentState.SUBMITTING], IntentState.REJECTED)
            return IntentState.REJECTED

        self.store.upsert_broker_observation(
            BrokerObservation(
                intent_id=intent.intent_id,
                broker="binance-spot-testnet",
                broker_order_id=submitted.broker_order_id,
                broker_status=submitted.status,
                reconciliation_required=submitted.status not in {"FILLED", "CANCELED", "REJECTED", "EXPIRED"},
                observed_at=datetime.now(timezone.utc),
            )
        )
        target = {
            "FILLED": IntentState.FILLED,
            "PARTIALLY_FILLED": IntentState.PARTIALLY_FILLED,
            "REJECTED": IntentState.REJECTED,
            "CANCELED": IntentState.CANCELLED,
            "EXPIRED": IntentState.CANCELLED,
        }.get(submitted.status, IntentState.ACKNOWLEDGED)
        self.store.transition(intent.intent_id, [IntentState.SUBMITTING], target)
        return target
