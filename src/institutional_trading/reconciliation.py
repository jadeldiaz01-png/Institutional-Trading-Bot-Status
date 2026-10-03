from __future__ import annotations

from dataclasses import dataclass

from .domain import IntentState


@dataclass(frozen=True)
class BrokerObservation:
    found: bool
    status: str | None
    filled_quantity: str | None = None


class Reconciler:
    """Deterministic reconciliation for ambiguous submissions.

    Network timeout or broker ambiguity must never be treated as rejection or success.
    UNKNOWN remains blocked until a broker observation resolves it.
    """

    def resolve(self, current: IntentState, observation: BrokerObservation) -> IntentState:
        if current not in {IntentState.SUBMITTING, IntentState.UNKNOWN, IntentState.PARTIALLY_FILLED}:
            return current
        if not observation.found:
            return IntentState.UNKNOWN

        mapping = {
            "NEW": IntentState.ACKNOWLEDGED,
            "PARTIALLY_FILLED": IntentState.PARTIALLY_FILLED,
            "FILLED": IntentState.FILLED,
            "CANCELED": IntentState.CANCELLED,
            "CANCELLED": IntentState.CANCELLED,
            "REJECTED": IntentState.REJECTED,
            "EXPIRED": IntentState.CANCELLED,
        }
        return mapping.get((observation.status or "").upper(), IntentState.UNKNOWN)
