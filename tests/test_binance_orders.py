from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from binance_mcp.binance_orders import (
    AmbiguousSubmissionError,
    BinanceOrderClient,
    ExecutionNotAuthorized,
    OrderRejectedError,
)
from binance_mcp.contracts import OrderRecord, OrderState, TradeIntent


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64


class FakeResponse:
    def __init__(self, payload, status=200):
        self.status = status
        self._body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._body


def intent(environment="TESTNET"):
    return TradeIntent(
        account_alias="spot-primary",
        environment=environment,
        symbol="BTCUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity="0.001",
        quote_quantity=None,
        price="50000.00",
        stop_price=None,
        time_in_force="GTC",
        max_slippage_bps="25",
        max_notional="100.00",
        strategy_id="manual-reviewed",
        strategy_version="1",
        risk_snapshot_sha256=SHA_A,
        model_bundle_sha256=SHA_B,
        market_snapshot_sha256=SHA_C,
        exchange_info_sha256=SHA_D,
        created_at_ms=1_800_000_000_000,
        expires_at_ms=1_800_000_060_000,
    )


def record(state=OrderState.HUMAN_APPROVED, environment="TESTNET"):
    i = intent(environment)
    digest = i.intent_sha256()
    return i, OrderRecord(
        order_id="ord-1",
        intent_sha256=digest,
        idempotency_key=digest,
        client_order_id="agia-1234567890abcdef",
        state=state,
        authorization_id="approval-1" if state == OrderState.HUMAN_APPROVED else None,
    )


class BinanceOrderTests(unittest.TestCase):
    def client(self, i, *, environment="TESTNET", live_enabled=False):
        return BinanceOrderClient(
            api_key="test-key",
            api_secret="test-secret",
            environment=environment,
            intent_lookup=lambda sha: i if sha == i.intent_sha256() else None,
            clock_ms=lambda: 1_800_000_001_000,
            live_enabled=live_enabled,
        )

    @patch("binance_mcp.binance_orders.urlopen")
    def test_testnet_submit_uses_exact_client_id_and_signed_order_shape(self, urlopen):
        i, order = record()
        urlopen.return_value = FakeResponse({
            "symbol": "BTCUSDT",
            "orderId": 123,
            "clientOrderId": order.client_order_id,
            "status": "NEW",
        })
        submission = self.client(i).submit_approved(order)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.method, "POST")
        self.assertTrue(request.full_url.startswith("https://testnet.binance.vision/api/v3/order?"))
        self.assertIn(f"newClientOrderId={order.client_order_id}", request.full_url)
        self.assertIn("symbol=BTCUSDT", request.full_url)
        self.assertIn("side=BUY", request.full_url)
        self.assertIn("type=LIMIT", request.full_url)
        self.assertIn("quantity=0.001", request.full_url)
        self.assertIn("price=50000.00", request.full_url)
        self.assertIn("timeInForce=GTC", request.full_url)
        self.assertIn("signature=", request.full_url)
        self.assertEqual(request.headers["X-mbx-apikey"], "test-key")
        self.assertEqual(submission.client_order_id, order.client_order_id)
        self.assertEqual(submission.exchange_order_id, "123")
        self.assertEqual(submission.status, "NEW")

    @patch("binance_mcp.binance_orders.urlopen")
    def test_submit_requires_human_approved_state(self, urlopen):
        i, order = record(OrderState.RISK_APPROVED)
        with self.assertRaises(ExecutionNotAuthorized):
            self.client(i).submit_approved(order)
        urlopen.assert_not_called()

    @patch("binance_mcp.binance_orders.urlopen")
    def test_timeout_is_ambiguous_and_is_never_retried(self, urlopen):
        i, order = record()
        urlopen.side_effect = TimeoutError("ambiguous")
        with self.assertRaises(AmbiguousSubmissionError):
            self.client(i).submit_approved(order)
        self.assertEqual(urlopen.call_count, 1)

    @patch("binance_mcp.binance_orders.urlopen")
    def test_http_4xx_is_rejected_without_retry(self, urlopen):
        i, order = record()
        urlopen.side_effect = HTTPError(
            url="https://testnet.binance.vision/api/v3/order",
            code=400,
            msg="bad order",
            hdrs=None,
            fp=io.BytesIO(b'{"code":-1013,"msg":"invalid quantity"}'),
        )
        with self.assertRaises(OrderRejectedError):
            self.client(i).submit_approved(order)
        self.assertEqual(urlopen.call_count, 1)

    @patch("binance_mcp.binance_orders.urlopen")
    def test_http_5xx_is_ambiguous_not_rejected(self, urlopen):
        i, order = record()
        urlopen.side_effect = HTTPError(
            url="https://testnet.binance.vision/api/v3/order",
            code=503,
            msg="unavailable",
            hdrs=None,
            fp=io.BytesIO(b""),
        )
        with self.assertRaises(AmbiguousSubmissionError):
            self.client(i).submit_approved(order)
        self.assertEqual(urlopen.call_count, 1)

    def test_live_endpoint_is_impossible_without_explicit_live_enable(self):
        i, _ = record(environment="LIVE_PILOT")
        with self.assertRaises(ExecutionNotAuthorized):
            self.client(i, environment="LIVE_PILOT", live_enabled=False)

    def test_forbidden_funds_movement_capabilities_do_not_exist(self):
        i, _ = record()
        client = self.client(i)
        for name in ("withdraw", "transfer", "internal_transfer", "universal_transfer"):
            self.assertFalse(hasattr(client, name), name)


if __name__ == "__main__":
    unittest.main()
