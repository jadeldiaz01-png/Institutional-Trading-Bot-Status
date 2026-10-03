"""Fail-closed order state machine for governed Binance execution."""

from __future__ import annotations

from .contracts import OrderRecord, OrderState
from .store import DuplicateOrderError, OrderStore


class InvalidTransition(RuntimeError):
    pass


_ALLOWED: dict[OrderState, set[OrderState]] = {
    OrderState.PROPOSED: {OrderState.VALIDATED, OrderState.REJECTED, OrderState.EXPIRED},
    OrderState.VALIDATED: {OrderState.RISK_APPROVED, OrderState.REJECTED, OrderState.EXPIRED},
    OrderState.RISK_APPROVED: {
        OrderState.HUMAN_APPROVAL_PENDING,
        OrderState.REJECTED,
        OrderState.EXPIRED,
    },
    OrderState.HUMAN_APPROVAL_PENDING: {
        OrderState.HUMAN_APPROVED,
        OrderState.REJECTED,
        OrderState.EXPIRED,
    },
    OrderState.HUMAN_APPROVED: {OrderState.SUBMITTING, OrderState.EXPIRED},
    OrderState.SUBMITTING: {
        OrderState.ACKNOWLEDGED,
        OrderState.UNKNOWN,
        OrderState.REJECTED,
    },
    OrderState.ACKNOWLEDGED: {
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.UNKNOWN,
        OrderState.REJECTED,
    },
    OrderState.PARTIALLY_FILLED: {
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.UNKNOWN,
    },
    OrderState.UNKNOWN: {OrderState.RECONCILED},
    OrderState.FILLED: {OrderState.RECONCILED},
    OrderState.CANCELLED: {OrderState.RECONCILED},
    OrderState.REJECTED: {OrderState.RECONCILED},
    OrderState.EXPIRED: {OrderState.RECONCILED},
    OrderState.RECONCILED: set(),
}


class OMS:
    def __init__(self, store: OrderStore):
        self.store = store

    def transition(
        self,
        order_id: str,
        target: OrderState,
        *,
        evidence: dict[str, str],
    ) -> OrderRecord:
        current = self.store.get(order_id)
        if target not in _ALLOWED[current.state]:
            raise InvalidTransition(f"illegal transition {current.state.value}->{target.value}")

        authorization_id = current.authorization_id
        reconciliation_id = current.reconciliation_id

        if target == OrderState.HUMAN_APPROVED:
            authorization_id = evidence.get("authorization_id")
            if not authorization_id:
                raise InvalidTransition("authorization evidence required")
        elif current.state in {
            OrderState.HUMAN_APPROVED,
            OrderState.SUBMITTING,
            OrderState.ACKNOWLEDGED,
            OrderState.PARTIALLY_FILLED,
            OrderState.UNKNOWN,
            OrderState.FILLED,
            OrderState.CANCELLED,
            OrderState.REJECTED,
            OrderState.EXPIRED,
        } and not authorization_id:
            raise InvalidTransition("existing authorization evidence missing")

        if target == OrderState.RECONCILED:
            reconciliation_id = evidence.get("reconciliation_id")
            if not reconciliation_id:
                raise InvalidTransition("reconciliation evidence required")

        updated = OrderRecord(
            order_id=current.order_id,
            intent_sha256=current.intent_sha256,
            idempotency_key=current.idempotency_key,
            client_order_id=current.client_order_id,
            state=target,
            authorization_id=authorization_id,
            reconciliation_id=reconciliation_id,
        )
        return self.store.save(updated)


__all__ = ["DuplicateOrderError", "InvalidTransition", "OMS"]
