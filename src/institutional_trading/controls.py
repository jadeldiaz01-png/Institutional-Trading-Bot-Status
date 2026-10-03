from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .domain import Environment, OrderIntent


class ControlUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Decision:
    allowed: bool
    decision_ref: str
    reason: str


class PolicyEngine:
    def evaluate(self, intent: OrderIntent, *, live_trading_enabled: bool) -> Decision:
        if intent.environment == Environment.PROD and not live_trading_enabled:
            return Decision(False, "policy:live-disabled", "LIVE_TRADING_ENABLED=false")
        if intent.environment == Environment.PROD and not intent.approval_ref:
            return Decision(False, "policy:approval-required", "human approval missing")
        return Decision(True, "policy:baseline-v1", "baseline policy passed")


@dataclass(frozen=True)
class RiskLimits:
    max_notional: Decimal
    max_quantity: Decimal


class RiskEngine:
    def __init__(self, limits: RiskLimits | None) -> None:
        self._limits = limits

    def evaluate(self, intent: OrderIntent, *, reference_price: Decimal | None) -> Decision:
        if self._limits is None:
            raise ControlUnavailable("risk limits unavailable")
        if reference_price is None or reference_price <= 0:
            return Decision(False, "risk:no-price", "reference price unavailable")
        if intent.quantity > self._limits.max_quantity:
            return Decision(False, "risk:max-quantity", "quantity exceeds hard limit")
        notional = intent.quantity * reference_price
        if notional > self._limits.max_notional:
            return Decision(False, "risk:max-notional", "notional exceeds hard limit")
        return Decision(True, "risk:baseline-v1", "hard limits passed")


class KillSwitches:
    def __init__(self) -> None:
        self._global = False
        self._strategies: set[str] = set()

    def engage_global(self) -> None:
        self._global = True

    def engage_strategy(self, strategy_id: str) -> None:
        self._strategies.add(strategy_id)

    def assert_clear(self, intent: OrderIntent) -> None:
        if self._global or intent.strategy_id in self._strategies:
            raise ControlUnavailable("kill switch engaged")
