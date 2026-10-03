from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("binance_mcp_cli", ROOT / "scripts/binance_mcp_cli.py")
assert SPEC is not None and SPEC.loader is not None
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)


class BinanceMCPCLITests(unittest.TestCase):
    def write_request(self, root: Path, payload: dict, name="request.json") -> Path:
        path = root / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_read_operation_dispatches_only_to_fixed_handler(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = self.write_request(root, {"symbol": "BTCUSDT"})
            calls = []
            result = CLI.run_cli(
                ["--operation", "binance.market.ticker", "--request", str(request)],
                handlers={"binance.market.ticker": lambda payload: calls.append(payload) or {"price": "1"}},
                request_root=root,
            )
        self.assertEqual(calls, [{"symbol": "BTCUSDT"}])
        self.assertEqual(result, {"price": "1"})

    def test_unknown_and_forbidden_operations_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = self.write_request(root, {})
            for operation in (
                "unknown.operation",
                "binance.withdraw.create",
                "binance.transfer.internal",
                "binance.margin.borrow",
                "binance.futures.order",
                "binance.options.order",
            ):
                with self.subTest(operation=operation):
                    with self.assertRaises(CLI.BoundaryError):
                        CLI.run_cli(
                            ["--operation", operation, "--request", str(request)],
                            handlers={},
                            request_root=root,
                        )

    def test_request_file_cannot_escape_request_root(self):
        with tempfile.TemporaryDirectory() as root_tmp, tempfile.TemporaryDirectory() as outside_tmp:
            root = Path(root_tmp)
            outside = self.write_request(Path(outside_tmp), {})
            with self.assertRaises(CLI.BoundaryError):
                CLI.run_cli(
                    ["--operation", "binance.market.ticker", "--request", str(outside)],
                    handlers={"binance.market.ticker": lambda payload: payload},
                    request_root=root,
                )

    def test_privileged_request_control_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for key in ("url", "command", "shell", "module"):
                request = self.write_request(root, {key: "attacker-controlled"}, name=f"{key}.json")
                with self.subTest(key=key):
                    with self.assertRaises(CLI.BoundaryError):
                        CLI.run_cli(
                            ["--operation", "binance.market.ticker", "--request", str(request)],
                            handlers={"binance.market.ticker": lambda payload: payload},
                            request_root=root,
                        )

    def test_side_effecting_operation_requires_exact_approval_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            incomplete = self.write_request(root, {"intent_sha256": "a" * 64}, "incomplete.json")
            with self.assertRaises(CLI.BoundaryError):
                CLI.run_cli(
                    ["--operation", "binance.order.execute_approved", "--request", str(incomplete)],
                    handlers={"binance.order.execute_approved": lambda payload: payload},
                    request_root=root,
                )

            complete = self.write_request(
                root,
                {
                    "intent_sha256": "a" * 64,
                    "approval": {
                        "approval_id": "approval-1",
                        "intent_sha256": "a" * 64,
                        "nonce": "nonce-1",
                    },
                },
                "complete.json",
            )
            result = CLI.run_cli(
                ["--operation", "binance.order.execute_approved", "--request", str(complete)],
                handlers={"binance.order.execute_approved": lambda payload: {"accepted": True}},
                request_root=root,
            )
            self.assertEqual(result, {"accepted": True})

    def test_sensitive_output_keys_are_redacted_recursively(self):
        value = CLI.redact_output(
            {
                "ok": True,
                "api_secret": "secret-value",
                "nested": {"authorization": "Bearer x", "token": "abc", "safe": "yes"},
            }
        )
        self.assertEqual(value["ok"], True)
        self.assertEqual(value["api_secret"], "[REDACTED]")
        self.assertEqual(value["nested"]["authorization"], "[REDACTED]")
        self.assertEqual(value["nested"]["token"], "[REDACTED]")
        self.assertEqual(value["nested"]["safe"], "yes")


if __name__ == "__main__":
    unittest.main()
