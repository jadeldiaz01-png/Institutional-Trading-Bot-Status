"""Independent fail-closed trading kill-switch gate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .contracts import RiskDecision
from .risk import SystemHealth


@dataclass(frozen=True)
class ReconciliationState:
    clean: bool
    unresolved_unknown: int

    def __post_init__(self) -> None:
        if self.unresolved_unknown < 0:
            raise ValueError("unresolved_unknown must be nonnegative")


@dataclass(frozen=True)
class KillSwitchState:
    global_halt: bool = False
    halted_accounts: tuple[str, ...] = ()
    halted_strategies: tuple[str, ...] = ()


@dataclass(frozen=True)
class KillSwitchDecision:
    decision: Literal["ALLOW", "DENY"]
    reasons: tuple[str, ...]
    execution_authorized: bool = False


class KillSwitch:
    def __init__(self, state: KillSwitchState):
        self.state = state

    def evaluate(
        self,
        *,
        system_health: SystemHealth,
        permission_policy: RiskDecision,
        reconciliation_state: ReconciliationState,
        account_alias: str,
        strategy_id: str,
    ) -> KillSwitchDecision:
        reasons: list[str] = []

        if self.state.global_halt:
            reasons.append("GLOBAL_KILL_SWITCH")
        if account_alias in self.state.halted_accounts:
            reasons.append("ACCOUNT_KILL_SWITCH")
        if strategy_id in self.state.halted_strategies:
            reasons.append("STRATEGY_KILL_SWITCH")

        if not system_health.healthy():
            reasons.append("SYSTEM_HEALTH_DENY")
        if not permission_policy.allowed:
            reasons.append("PERMISSION_POLICY_DENY")
        if not reconciliation_state.clean or reconciliation_state.unresolved_unknown > 0:
            reasons.append("RECONCILIATION_NOT_CLEAN")

        deduped = tuple(dict.fromkeys(reasons))
        return KillSwitchDecision(
            decision="DENY" if deduped else "ALLOW",
            reasons=deduped,
            # Passing this gate never grants financial authority.
            execution_authorized=False,
        )
