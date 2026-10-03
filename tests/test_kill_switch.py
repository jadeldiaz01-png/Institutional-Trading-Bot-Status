from __future__ import annotations

import unittest

from binance_mcp.contracts import RiskDecision
from binance_mcp.kill_switch import KillSwitch, KillSwitchState, ReconciliationState
from binance_mcp.risk import SystemHealth


SHA = "a" * 64


def healthy(**overrides):
    values = {
        "binance_connected": True,
        "websocket_healthy": True,
        "clock_synchronized": True,
        "reconciliation_clean": True,
        "telemetry_healthy": True,
        "policy_healthy": True,
        "secrets_healthy": True,
        "permissions_healthy": True,
        "kill_switch_clear": True,
    }
    values.update(overrides)
    return SystemHealth(**values)


def permission(allowed=True):
    return RiskDecision(
        allowed=allowed,
        reasons=() if allowed else ("enableWithdrawals=forbidden_true",),
        snapshot_sha256=SHA,
    )


class KillSwitchTests(unittest.TestCase):
    def test_clean_system_allows_candidate_to_continue_without_authorizing_execution(self):
        switch = KillSwitch(KillSwitchState())
        result = switch.evaluate(
            system_health=healthy(),
            permission_policy=permission(True),
            reconciliation_state=ReconciliationState(clean=True, unresolved_unknown=0),
            account_alias="spot-primary",
            strategy_id="manual-reviewed",
        )
        self.assertEqual(result.decision, "ALLOW")
        self.assertEqual(result.reasons, ())
        self.assertFalse(result.execution_authorized)

    def test_permission_drift_reconciliation_and_telemetry_failures_deny(self):
        cases = [
            (
                "permission",
                healthy(),
                permission(False),
                ReconciliationState(clean=True, unresolved_unknown=0),
                "PERMISSION_POLICY_DENY",
            ),
            (
                "unknown",
                healthy(),
                permission(True),
                ReconciliationState(clean=False, unresolved_unknown=1),
                "RECONCILIATION_NOT_CLEAN",
            ),
            (
                "telemetry",
                healthy(telemetry_healthy=False),
                permission(True),
                ReconciliationState(clean=True, unresolved_unknown=0),
                "SYSTEM_HEALTH_DENY",
            ),
        ]
        for name, health, permissions, reconciliation, reason in cases:
            with self.subTest(name=name):
                result = KillSwitch(KillSwitchState()).evaluate(
                    system_health=health,
                    permission_policy=permissions,
                    reconciliation_state=reconciliation,
                    account_alias="spot-primary",
                    strategy_id="manual-reviewed",
                )
                self.assertEqual(result.decision, "DENY")
                self.assertIn(reason, result.reasons)
                self.assertFalse(result.execution_authorized)

    def test_global_account_and_strategy_scopes_deny_independently(self):
        states = [
            (KillSwitchState(global_halt=True), "GLOBAL_KILL_SWITCH"),
            (KillSwitchState(halted_accounts=("spot-primary",)), "ACCOUNT_KILL_SWITCH"),
            (KillSwitchState(halted_strategies=("manual-reviewed",)), "STRATEGY_KILL_SWITCH"),
        ]
        for state, reason in states:
            with self.subTest(reason=reason):
                result = KillSwitch(state).evaluate(
                    system_health=healthy(),
                    permission_policy=permission(True),
                    reconciliation_state=ReconciliationState(clean=True, unresolved_unknown=0),
                    account_alias="spot-primary",
                    strategy_id="manual-reviewed",
                )
                self.assertEqual(result.decision, "DENY")
                self.assertIn(reason, result.reasons)

    def test_invalid_reconciliation_counts_fail_closed(self):
        with self.assertRaises(ValueError):
            ReconciliationState(clean=True, unresolved_unknown=-1)


if __name__ == "__main__":
    unittest.main()
