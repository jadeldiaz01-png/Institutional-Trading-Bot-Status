"""Exact-intent, one-time human approval verification."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Protocol

from .contracts import OrderApproval, TradeIntent


@dataclass(frozen=True)
class ApprovalResult:
    allowed: bool
    reasons: tuple[str, ...]
    approval_id: str | None = None


class ApprovalNonceStore(Protocol):
    def consume(self, nonce: str) -> bool:
        """Atomically consume nonce; return False if it was already consumed."""


class InMemoryApprovalNonceStore:
    """Reference atomic nonce store for tests and non-durable environments."""

    def __init__(self) -> None:
        self._used: set[str] = set()
        self._lock = Lock()

    def consume(self, nonce: str) -> bool:
        with self._lock:
            if nonce in self._used:
                return False
            self._used.add(nonce)
            return True


_BOUND_FIELDS = (
    "account_alias",
    "environment",
    "symbol",
    "side",
    "order_type",
    "quantity",
    "quote_quantity",
    "price",
    "stop_price",
    "time_in_force",
    "max_slippage_bps",
    "max_notional",
    "strategy_id",
    "strategy_version",
    "risk_snapshot_sha256",
    "model_bundle_sha256",
    "market_snapshot_sha256",
    "exchange_info_sha256",
)


class ApprovalVerifier:
    def __init__(self, nonce_store: ApprovalNonceStore):
        self._nonce_store = nonce_store

    def verify(
        self,
        intent: TradeIntent,
        approval: OrderApproval,
        *,
        now_ms: int,
    ) -> ApprovalResult:
        reasons: list[str] = []

        if now_ms < 0:
            reasons.append("INVALID_CLOCK")
        if now_ms < approval.created_at_ms:
            reasons.append("APPROVAL_NOT_YET_VALID")
        if now_ms > approval.expires_at_ms:
            reasons.append("APPROVAL_EXPIRED")
        if (
            approval.created_at_ms < intent.created_at_ms
            or approval.expires_at_ms > intent.expires_at_ms
        ):
            reasons.append("APPROVAL_WINDOW_OUTSIDE_INTENT")

        if approval.intent_sha256 != intent.intent_sha256():
            reasons.append("APPROVAL_INTENT_MISMATCH")
        else:
            for name in _BOUND_FIELDS:
                if getattr(approval, name) != getattr(intent, name):
                    reasons.append("APPROVAL_INTENT_MISMATCH")
                    break

        if reasons:
            return ApprovalResult(
                allowed=False,
                reasons=tuple(dict.fromkeys(reasons)),
                approval_id=approval.approval_id,
            )

        if not self._nonce_store.consume(approval.nonce):
            return ApprovalResult(
                allowed=False,
                reasons=("NONCE_ALREADY_USED",),
                approval_id=approval.approval_id,
            )

        return ApprovalResult(
            allowed=True,
            reasons=(),
            approval_id=approval.approval_id,
        )
