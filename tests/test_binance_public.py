from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from binance_mcp.binance_public import BinancePublicClient, ProviderError


class FakeResponse:
    def __init__(self, payload, *, status=200):
        self.status = status
        if isinstance(payload, bytes):
            self._body = payload
        else:
            self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._body


def exchange_info(*, tick="0.10", step="0.001", min_notional="10.00"):
    return {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "status": "TRADING",
                "orderTypes": ["LIMIT", "MARKET"],
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": tick},
                    {
                        "filterType": "LOT_SIZE",
                        "stepSize": step,
                        "minQty": "0.001",
                        "maxQty": "100.000",
                    },
                    {"filterType": "MIN_NOTIONAL", "minNotional": min_notional},
                ],
            }
        ]
    }


class BinancePublicTests(unittest.TestCase):
    def test_rejects_non_allowlisted_or_non_https_base_url(self):
        with self.assertRaises(ProviderError):
            BinancePublicClient(base_url="http://api.binance.com").ticker("BTCUSDT")
        with self.assertRaises(ProviderError):
            BinancePublicClient(base_url="https://example.com").ticker("BTCUSDT")

    @patch("binance_mcp.binance_public.urlopen")
    def test_market_methods_use_expected_public_shapes(self, urlopen):
        urlopen.side_effect = [
            FakeResponse({"symbol": "BTCUSDT", "price": "50000.00"}),
            FakeResponse([[1, "1", "2", "0.5", "1.5", "100"]]),
            FakeResponse({"lastUpdateId": 1, "bids": [["1", "2"]], "asks": [["2", "1"]]}),
            FakeResponse([{"id": 1, "price": "50000.00", "qty": "0.1"}]),
        ]
        client = BinancePublicClient()
        self.assertEqual(client.ticker("BTCUSDT")["symbol"], "BTCUSDT")
        self.assertEqual(len(client.klines("BTCUSDT", "1m", 1)), 1)
        self.assertIn("bids", client.order_book("BTCUSDT", 5))
        self.assertEqual(client.recent_trades("BTCUSDT", 1)[0]["id"], 1)

    @patch("binance_mcp.binance_public.urlopen")
    def test_malformed_json_and_unexpected_schema_fail_closed(self, urlopen):
        urlopen.side_effect = [
            FakeResponse(b"{not-json"),
            FakeResponse([]),
        ]
        client = BinancePublicClient()
        with self.assertRaises(ProviderError):
            client.ticker("BTCUSDT")
        with self.assertRaises(ProviderError):
            client.ticker("BTCUSDT")

    @patch("binance_mcp.binance_public.urlopen")
    def test_http_error_is_normalized(self, urlopen):
        urlopen.side_effect = HTTPError(
            url="https://api.binance.com/api/v3/ticker/price",
            code=429,
            msg="rate limited",
            hdrs=None,
            fp=io.BytesIO(b""),
        )
        with self.assertRaises(ProviderError):
            BinancePublicClient().ticker("BTCUSDT")

    @patch("binance_mcp.binance_public.urlopen")
    def test_unknown_symbol_fails_closed(self, urlopen):
        urlopen.return_value = FakeResponse(exchange_info())
        with self.assertRaises(ProviderError):
            BinancePublicClient().symbol_filters("ETHUSDT")

    @patch("binance_mcp.binance_public.urlopen")
    def test_symbol_filters_are_discovered_dynamically(self, urlopen):
        urlopen.side_effect = [
            FakeResponse(exchange_info(tick="0.10", step="0.001", min_notional="10.00")),
            FakeResponse(exchange_info(tick="0.01", step="0.0001", min_notional="25.00")),
        ]
        client = BinancePublicClient()
        first = client.symbol_filters("BTCUSDT")
        second = client.symbol_filters("BTCUSDT")
        self.assertEqual(first.tick_size, "0.10")
        self.assertEqual(first.step_size, "0.001")
        self.assertEqual(first.min_notional, "10.00")
        self.assertEqual(second.tick_size, "0.01")
        self.assertEqual(second.step_size, "0.0001")
        self.assertEqual(second.min_notional, "25.00")

    @patch("binance_mcp.binance_public.urlopen")
    def test_missing_required_filter_is_rejected(self, urlopen):
        payload = exchange_info()
        payload["symbols"][0]["filters"] = [
            item for item in payload["symbols"][0]["filters"]
            if item["filterType"] != "LOT_SIZE"
        ]
        urlopen.return_value = FakeResponse(payload)
        with self.assertRaises(ProviderError):
            BinancePublicClient().symbol_filters("BTCUSDT")


if __name__ == "__main__":
    unittest.main()
