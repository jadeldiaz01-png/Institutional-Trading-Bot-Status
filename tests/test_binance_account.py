from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from binance_mcp.binance_account import BinanceAccountClient, PermissionPolicy
from binance_mcp.binance_auth import BinanceSigner


class FakeResponse:
    def __init__(self, payload):
        self.status = 200
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._body


class BinanceAccountTests(unittest.TestCase):
    def test_signer_percent_encodes_and_pins_deterministic_hmac(self):
        signer = BinanceSigner(api_key="test-key", api_secret="test-secret")
        signed = signer.sign(
            "GET",
            "/api/v3/allOrders",
            {"symbol": "BTCUSDT"},
            timestamp_ms=1770736694138,
            recv_window_ms=5000,
        )
        self.assertEqual(
            signed.query_string,
            "recvWindow=5000&symbol=BTCUSDT&timestamp=1770736694138",
        )
        self.assertEqual(
            signed.signature,
            "f06f90b144540fefd63f28c5cc807e123be885a7e0baaf7debd4c612e650edfd",
        )
        self.assertNotIn("test-secret", repr(signed))

    def test_signer_rejects_invalid_recv_window(self):
        signer = BinanceSigner(api_key="test-key", api_secret="test-secret")
        with self.assertRaises(ValueError):
            signer.sign("GET", "/api/v3/account", {}, timestamp_ms=1, recv_window_ms=0)
        with self.assertRaises(ValueError):
            signer.sign("GET", "/api/v3/account", {}, timestamp_ms=1, recv_window_ms=60001)

    def test_permission_policy_denies_privilege_drift(self):
        policy = PermissionPolicy.read_only()
        safe = {
            "enableReading": True,
            "enableSpotAndMarginTrading": False,
            "enableWithdrawals": False,
            "enableInternalTransfer": False,
            "permitsUniversalTransfer": False,
            "enableMargin": False,
            "enableFutures": False,
            "enableVanillaOptions": False,
            "enablePortfolioMarginTrading": False,
        }
        decision = policy.evaluate_payload(safe)
        self.assertTrue(decision.allowed)

        for key in (
            "enableSpotAndMarginTrading",
            "enableWithdrawals",
            "enableInternalTransfer",
            "permitsUniversalTransfer",
            "enableMargin",
            "enableFutures",
            "enableVanillaOptions",
            "enablePortfolioMarginTrading",
        ):
            drifted = dict(safe)
            drifted[key] = True
            denied = policy.evaluate_payload(drifted)
            self.assertFalse(denied.allowed, key)
            self.assertTrue(any(key in reason for reason in denied.reasons))

    def test_permission_policy_denies_missing_read_permission(self):
        denied = PermissionPolicy.read_only().evaluate_payload({"enableReading": False})
        self.assertFalse(denied.allowed)
        self.assertIn("enableReading", " ".join(denied.reasons))

    @patch("binance_mcp.binance_account.urlopen")
    def test_account_client_uses_file_backed_credentials_and_read_only_endpoints(self, urlopen):
        urlopen.side_effect = [
            FakeResponse({"data": "Normal"}),
            FakeResponse({
                "enableReading": True,
                "enableSpotAndMarginTrading": False,
                "enableWithdrawals": False,
                "enableInternalTransfer": False,
                "permitsUniversalTransfer": False,
                "enableMargin": False,
                "enableFutures": False,
            }),
            FakeResponse({"balances": [{"asset": "USDT", "free": "100", "locked": "0"}]}),
            FakeResponse([]),
            FakeResponse([]),
            FakeResponse([]),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key_file = root / "api-key"
            secret_file = root / "api-secret"
            key_file.write_text("test-key\n", encoding="utf-8")
            secret_file.write_text("test-secret\n", encoding="utf-8")
            client = BinanceAccountClient.from_credential_files(
                api_key_file=key_file,
                api_secret_file=secret_file,
                clock_ms=lambda: 1770736694138,
            )

            self.assertEqual(client.account_status()["data"], "Normal")
            self.assertTrue(client.permissions().read)
            self.assertEqual(client.balances()[0]["asset"], "USDT")
            self.assertEqual(client.open_orders("BTCUSDT"), [])
            self.assertEqual(client.order_history("BTCUSDT"), [])
            self.assertEqual(client.trade_history("BTCUSDT"), [])

        requested = [call.args[0].full_url for call in urlopen.call_args_list]
        self.assertTrue(any("/sapi/v1/account/status?" in url for url in requested))
        self.assertTrue(any("/sapi/v1/account/apiRestrictions?" in url for url in requested))
        self.assertTrue(any("/api/v3/account?" in url for url in requested))
        self.assertTrue(any("/api/v3/openOrders?" in url for url in requested))
        self.assertTrue(any("/api/v3/allOrders?" in url for url in requested))
        self.assertTrue(any("/api/v3/myTrades?" in url for url in requested))
        self.assertFalse(any("/api/v3/order?" in url for url in requested))

    def test_credential_files_reject_empty_or_multiline_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key_file = root / "api-key"
            secret_file = root / "api-secret"
            key_file.write_text("", encoding="utf-8")
            secret_file.write_text("secret\nsecond-line\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                BinanceAccountClient.from_credential_files(
                    api_key_file=key_file,
                    api_secret_file=secret_file,
                )


if __name__ == "__main__":
    unittest.main()
