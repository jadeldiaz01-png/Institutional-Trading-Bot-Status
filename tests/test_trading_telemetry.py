from __future__ import annotations

import json
import unittest

from binance_mcp.telemetry import TradingAuditEvent, sanitize_telemetry


class TradingTelemetryTests(unittest.TestCase):
    def test_sensitive_fields_are_redacted_and_private_reasoning_is_dropped(self):
        value = sanitize_telemetry(
            {
                "event": "decision",
                "api_secret": "super-secret",
                "api_key": "key-value",
                "authorization": "Bearer abc",
                "token": "token-value",
                "credential": "cred-value",
                "chain_of_thought": "private reasoning",
                "private_reasoning": "never persist",
                "raw_prompt": "hidden prompt",
                "nested": {
                    "safe": "kept",
                    "password": "pw",
                    "reasoning": "internal",
                },
            }
        )
        self.assertEqual(value["api_secret"], "[REDACTED]")
        self.assertEqual(value["api_key"], "[REDACTED]")
        self.assertEqual(value["authorization"], "[REDACTED]")
        self.assertEqual(value["token"], "[REDACTED]")
        self.assertEqual(value["credential"], "[REDACTED]")
        self.assertNotIn("chain_of_thought", value)
        self.assertNotIn("private_reasoning", value)
        self.assertNotIn("raw_prompt", value)
        self.assertEqual(value["nested"]["safe"], "kept")
        self.assertEqual(value["nested"]["password"], "[REDACTED]")
        self.assertNotIn("reasoning", value["nested"])

    def test_audit_event_serialization_contains_only_sanitized_bounded_details(self):
        event = TradingAuditEvent.build(
            event_type="ORDER_RISK_CHECK",
            run_id="run-1",
            request_id="req-1",
            outcome="DENY",
            timestamp_ms=1_800_000_000_000,
            details={
                "symbol": "BTCUSDT",
                "authorization": "Bearer secret",
                "chain_of_thought": "do not persist",
            },
        )
        payload = json.loads(event.to_json())
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["details"]["symbol"], "BTCUSDT")
        self.assertEqual(payload["details"]["authorization"], "[REDACTED]")
        self.assertNotIn("chain_of_thought", payload["details"])
        serialized = event.to_json()
        self.assertNotIn("Bearer secret", serialized)
        self.assertNotIn("do not persist", serialized)

    def test_audit_event_rejects_invalid_identity_or_oversized_details(self):
        with self.assertRaises(ValueError):
            TradingAuditEvent.build(
                event_type="",
                run_id="run-1",
                request_id="req-1",
                outcome="ALLOW",
                timestamp_ms=1,
                details={},
            )
        with self.assertRaises(ValueError):
            TradingAuditEvent.build(
                event_type="TEST",
                run_id="run-1",
                request_id="req-1",
                outcome="ALLOW",
                timestamp_ms=1,
                details={"blob": "x" * 70000},
            )


if __name__ == "__main__":
    unittest.main()
