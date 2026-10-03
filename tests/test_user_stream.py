from __future__ import annotations

import unittest

from binance_mcp.user_stream import UserStreamConsumer


def event(status="NEW", *, event_time=1_800_000_000_000, executed="0.000"):
    return {
        "e": "executionReport",
        "E": event_time,
        "s": "BTCUSDT",
        "c": "agia-123",
        "S": "BUY",
        "o": "LIMIT",
        "X": status,
        "i": 123,
        "x": "TRADE" if status in {"PARTIALLY_FILLED", "FILLED"} else "NEW",
        "l": executed,
        "z": executed,
    }


class UserStreamTests(unittest.TestCase):
    def test_duplicate_execution_reports_are_idempotent(self):
        consumer = UserStreamConsumer()
        first = consumer.on_event(event("NEW"))
        second = consumer.on_event(event("NEW"))
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0].client_order_id, "agia-123")
        self.assertEqual(first[0].order_status, "NEW")
        self.assertEqual(second, [])

    def test_order_status_events_are_normalized(self):
        consumer = UserStreamConsumer()
        statuses = ["NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "REJECTED", "EXPIRED"]
        for offset, status in enumerate(statuses):
            out = consumer.on_event(event(status, event_time=1_800_000_000_000 + offset, executed=str(offset)))
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0].order_status, status)

    def test_disconnect_suspends_execution_until_reconciliation(self):
        consumer = UserStreamConsumer()
        consumer.on_event(event())
        self.assertTrue(consumer.execution_allowed(now_ms=1_800_000_000_100, max_silence_ms=1000))
        consumer.mark_disconnected()
        self.assertFalse(consumer.execution_allowed(now_ms=1_800_000_000_100, max_silence_ms=1000))
        self.assertTrue(consumer.reconciliation_required)
        consumer.mark_reconciled(now_ms=1_800_000_000_200)
        self.assertTrue(consumer.execution_allowed(now_ms=1_800_000_000_300, max_silence_ms=1000))
        self.assertFalse(consumer.reconciliation_required)

    def test_stale_stream_suspends_new_execution(self):
        consumer = UserStreamConsumer()
        consumer.on_event(event(event_time=1_800_000_000_000))
        self.assertFalse(consumer.execution_allowed(now_ms=1_800_000_002_000, max_silence_ms=1000))

    def test_malformed_execution_report_fails_closed(self):
        consumer = UserStreamConsumer()
        with self.assertRaises(ValueError):
            consumer.on_event({"e": "executionReport", "E": 1})


if __name__ == "__main__":
    unittest.main()
