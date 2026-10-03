"""Fail-closed normalization of Binance Spot execution-report events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_ALLOWED_STATUSES = {
    "NEW",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCELED",
    "CANCELLED",
    "REJECTED",
    "EXPIRED",
}


@dataclass(frozen=True)
class OrderEvent:
    event_key: str
    event_time_ms: int
    client_order_id: str
    exchange_order_id: str
    symbol: str
    order_status: str


class UserStreamConsumer:
    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._trusted = False
        self._last_event_time_ms: int | None = None
        self.reconciliation_required = True

    def on_event(self, event: dict[str, Any]) -> list[OrderEvent]:
        if not isinstance(event, dict):
            raise ValueError("user stream event must be an object")
        if event.get("e") != "executionReport":
            return []

        required = ("E", "s", "c", "X", "i", "x", "l", "z")
        if any(name not in event for name in required):
            raise ValueError("malformed executionReport")
        if not isinstance(event["E"], int) or event["E"] < 0:
            raise ValueError("invalid executionReport event time")
        if not isinstance(event["c"], str) or not event["c"]:
            raise ValueError("invalid executionReport client order id")
        if not isinstance(event["s"], str) or not event["s"]:
            raise ValueError("invalid executionReport symbol")
        status = event["X"]
        if status not in _ALLOWED_STATUSES:
            raise ValueError("unsupported executionReport order status")

        key = "|".join(
            str(event[name])
            for name in ("E", "i", "c", "X", "x", "l", "z")
        )
        if key in self._seen:
            return []
        self._seen.add(key)
        self._last_event_time_ms = event["E"]
        self._trusted = True
        self.reconciliation_required = False
        return [
            OrderEvent(
                event_key=key,
                event_time_ms=event["E"],
                client_order_id=event["c"],
                exchange_order_id=str(event["i"]),
                symbol=event["s"],
                order_status=status,
            )
        ]

    def mark_disconnected(self) -> None:
        self._trusted = False
        self.reconciliation_required = True

    def mark_reconciled(self, *, now_ms: int) -> None:
        if now_ms < 0:
            raise ValueError("now_ms must be nonnegative")
        self._last_event_time_ms = now_ms
        self._trusted = True
        self.reconciliation_required = False

    def execution_allowed(self, *, now_ms: int, max_silence_ms: int) -> bool:
        if (
            now_ms < 0
            or max_silence_ms <= 0
            or not self._trusted
            or self.reconciliation_required
            or self._last_event_time_ms is None
        ):
            return False
        age = now_ms - self._last_event_time_ms
        return 0 <= age <= max_silence_ms
