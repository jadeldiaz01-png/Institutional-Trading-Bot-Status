from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from .binance_testnet import BinanceSpotTestnetAdapter, BrokerTimeoutUnknown
from .domain import IntentState
from .repository import BrokerObservation, PostgresStore


STATUS_MAP = {
    "NEW": IntentState.ACKNOWLEDGED,
    "PARTIALLY_FILLED": IntentState.PARTIALLY_FILLED,
    "FILLED": IntentState.FILLED,
    "CANCELED": IntentState.CANCELLED,
    "REJECTED": IntentState.REJECTED,
    "EXPIRED": IntentState.CANCELLED,
}


@dataclass(slots=True)
class ReconcileResult:
    intent_id: UUID
    state: IntentState
    reason: str


class ReconcilerWorker:
    def __init__(self, store: PostgresStore, adapter: BinanceSpotTestnetAdapter) -> None:
        self._store = store
        self._adapter = adapter

    def run_once(self, limit: int = 100) -> list[ReconcileResult]:
        results: list[ReconcileResult] = []
        for row in self._store.list_reconciliation_candidates(limit=limit):
            intent_id = row["intent_id"]
            try:
                observed = self._adapter.query_by_client_order_id(row["symbol"], row["client_order_id"])
            except BrokerTimeoutUnknown:
                self._store.transition(
                    intent_id,
                    [IntentState.SUBMITTING, IntentState.UNKNOWN, IntentState.PARTIALLY_FILLED],
                    IntentState.UNKNOWN,
                )
                results.append(ReconcileResult(intent_id, IntentState.UNKNOWN, "broker query timeout"))
                continue

            if observed is None:
                self._store.transition(
                    intent_id,
                    [IntentState.SUBMITTING, IntentState.UNKNOWN, IntentState.PARTIALLY_FILLED],
                    IntentState.UNKNOWN,
                )
                self._store.upsert_broker_observation(
                    BrokerObservation(intent_id, "binance-spot-testnet", None, None, True, datetime.now(timezone.utc))
                )
                results.append(ReconcileResult(intent_id, IntentState.UNKNOWN, "order not yet observable"))
                continue

            broker_status = str(observed.get("status", "UNKNOWN"))
            target = STATUS_MAP.get(broker_status, IntentState.UNKNOWN)
            self._store.upsert_broker_observation(
                BrokerObservation(
                    intent_id=intent_id,
                    broker="binance-spot-testnet",
                    broker_order_id=str(observed.get("orderId")) if observed.get("orderId") is not None else None,
                    broker_status=broker_status,
                    reconciliation_required=target == IntentState.UNKNOWN,
                    observed_at=datetime.now(timezone.utc),
                )
            )
            self._store.transition(
                intent_id,
                [IntentState.SUBMITTING, IntentState.UNKNOWN, IntentState.ACKNOWLEDGED, IntentState.PARTIALLY_FILLED],
                target,
            )
            results.append(ReconcileResult(intent_id, target, f"broker status={broker_status}"))
        return results
