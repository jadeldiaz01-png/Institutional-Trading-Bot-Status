from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from .controls import ControlUnavailable, Decision
from .domain import OrderIntent


@dataclass(slots=True)
class OPAClient:
    base_url: str
    timeout_seconds: float = 2.0

    def evaluate(self, intent: OrderIntent, *, risk_allowed: bool, kill_switch_clear: bool,
                 workload_verified: bool, audit_available: bool,
                 reconciliation_available: bool, live_trading_enabled: bool = False,
                 human_approvers: int = 0) -> Decision:
        payload: dict[str, Any] = {
            "input": {
                "environment": intent.environment.value,
                "live_trading_enabled": live_trading_enabled,
                "human_approval": {
                    "valid": bool(intent.approval_ref),
                    "approvers": human_approvers,
                },
                "risk": {"allowed": risk_allowed},
                "kill_switch_clear": kill_switch_clear,
                "identity": {"workload_verified": workload_verified},
                "audit_available": audit_available,
                "reconciliation_available": reconciliation_available,
            }
        }
        try:
            response = httpx.post(
                f"{self.base_url.rstrip('/')}/v1/data/trading/order_intent/allow",
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ControlUnavailable("OPA unavailable or invalid response") from exc
        allowed = body.get("result") is True
        return Decision(
            allowed=allowed,
            decision_ref=f"opa:{response.headers.get('x-request-id', 'decision')}",
            reason="OPA allow=true" if allowed else "OPA deny-by-default",
        )
