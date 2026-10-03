#!/usr/bin/env python3
"""Fixed-operation boundary between the private Runtime and Binance domain code."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable

from binance_mcp.binance_account import BinanceAccountClient
from binance_mcp.binance_public import BinancePublicClient


class BoundaryError(RuntimeError):
    pass


ALLOWED_OPERATIONS = {
    "binance.market.exchange_info",
    "binance.market.ticker",
    "binance.market.klines",
    "binance.market.order_book",
    "binance.market.recent_trades",
    "binance.account.status",
    "binance.account.permissions",
    "binance.account.balances",
    "binance.account.open_orders",
    "binance.account.order_history",
    "binance.account.trade_history",
    "binance.order.prepare",
    "binance.order.validate",
    "binance.order.risk_check",
    "binance.order.preview",
    "binance.order.execute_approved",
    "binance.order.cancel_approved",
    "binance.order.status",
    "binance.order.reconcile",
    "trading.decision.nemotron",
    "trading.decision.compare",
    "trading.decision.adjudicate",
}

SIDE_EFFECTING_OPERATIONS = {
    "binance.order.execute_approved",
    "binance.order.cancel_approved",
}

FORBIDDEN_MARKERS = ("withdraw", "transfer", "margin", "future", "option")
FORBIDDEN_CONTROL_KEYS = {"url", "command", "shell", "module"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SENSITIVE_KEY_MARKERS = ("token", "secret", "authorization", "credential", "api_key", "apikey")
MAX_REQUEST_BYTES = 128 * 1024
MAX_OUTPUT_BYTES = 256 * 1024


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--operation", required=True)
    parser.add_argument("--request", required=True)
    try:
        return parser.parse_args(argv)
    except SystemExit as exc:
        raise BoundaryError("invalid CLI arguments") from exc


def _validate_operation(operation: str) -> None:
    normalized = operation.strip().lower()
    if operation not in ALLOWED_OPERATIONS:
        raise BoundaryError("operation is not allowlisted")
    if any(marker in normalized for marker in FORBIDDEN_MARKERS):
        raise BoundaryError("forbidden trading capability")


def _reject_control_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).strip().lower() in FORBIDDEN_CONTROL_KEYS:
                raise BoundaryError(f"request control key is forbidden: {key}")
            _reject_control_keys(item)
    elif isinstance(value, list):
        for item in value:
            _reject_control_keys(item)


def _load_request(path: Path, request_root: Path) -> dict[str, Any]:
    root = request_root.resolve()
    resolved = path.resolve()
    if resolved == root or root not in resolved.parents:
        raise BoundaryError("request path escapes configured request root")
    if not resolved.is_file():
        raise BoundaryError("request file missing")
    if resolved.stat().st_size > MAX_REQUEST_BYTES:
        raise BoundaryError("request exceeds maximum size")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BoundaryError("request must be valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise BoundaryError("request must be a JSON object")
    _reject_control_keys(payload)
    return payload


def _validate_side_effect_envelope(operation: str, payload: dict[str, Any]) -> None:
    if operation not in SIDE_EFFECTING_OPERATIONS:
        return
    intent_sha = payload.get("intent_sha256")
    approval = payload.get("approval")
    if not isinstance(intent_sha, str) or SHA256_RE.fullmatch(intent_sha) is None:
        raise BoundaryError("side effect requires exact intent SHA-256")
    if not isinstance(approval, dict):
        raise BoundaryError("side effect requires approval envelope")
    if approval.get("intent_sha256") != intent_sha:
        raise BoundaryError("approval/intention hash mismatch")
    if not isinstance(approval.get("approval_id"), str) or not approval["approval_id"].strip():
        raise BoundaryError("approval_id required")
    if not isinstance(approval.get("nonce"), str) or not approval["nonce"].strip():
        raise BoundaryError("approval nonce required")


def redact_output(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).lower()
            if any(marker in normalized for marker in SENSITIVE_KEY_MARKERS):
                result[str(key)] = "[REDACTED]"
            else:
                result[str(key)] = redact_output(item)
        return result
    if isinstance(value, list):
        return [redact_output(item) for item in value]
    if isinstance(value, tuple):
        return [redact_output(item) for item in value]
    return value


def run_cli(
    argv: list[str],
    *,
    handlers: dict[str, Callable[[dict[str, Any]], Any]],
    request_root: Path,
) -> Any:
    args = _parse_args(argv)
    operation = str(args.operation)
    _validate_operation(operation)
    payload = _load_request(Path(args.request), request_root)
    _validate_side_effect_envelope(operation, payload)
    handler = handlers.get(operation)
    if handler is None:
        raise BoundaryError("operation handler is not configured")
    result = redact_output(handler(payload))
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise BoundaryError("handler output exceeds maximum size")
    return result


def _read_account_client() -> BinanceAccountClient:
    credentials_dir = Path(os.getenv("CREDENTIALS_DIRECTORY", "/run/credentials/universal-runtime-gateway"))
    return BinanceAccountClient.from_credential_files(
        api_key_file=credentials_dir / "binance_read_api_key",
        api_secret_file=credentials_dir / "binance_read_api_secret",
    )


def build_default_handlers() -> dict[str, Callable[[dict[str, Any]], Any]]:
    public = BinancePublicClient()

    def account() -> BinanceAccountClient:
        return _read_account_client()

    return {
        "binance.market.exchange_info": lambda p: public.exchange_info(p.get("symbol")),
        "binance.market.ticker": lambda p: public.ticker(str(p["symbol"])),
        "binance.market.klines": lambda p: public.klines(
            str(p["symbol"]), str(p["interval"]), int(p.get("limit", 500))
        ),
        "binance.market.order_book": lambda p: public.order_book(
            str(p["symbol"]), int(p.get("limit", 100))
        ),
        "binance.market.recent_trades": lambda p: public.recent_trades(
            str(p["symbol"]), int(p.get("limit", 100))
        ),
        "binance.account.status": lambda p: account().account_status(),
        "binance.account.permissions": lambda p: account().permissions().__dict__,
        "binance.account.balances": lambda p: account().balances(),
        "binance.account.open_orders": lambda p: account().open_orders(p.get("symbol")),
        "binance.account.order_history": lambda p: account().order_history(
            str(p["symbol"]), int(p.get("limit", 500))
        ),
        "binance.account.trade_history": lambda p: account().trade_history(
            str(p["symbol"]), int(p.get("limit", 500))
        ),
    }


def main(argv: list[str] | None = None) -> int:
    request_root = Path(os.getenv("BINANCE_MCP_REQUEST_ROOT", "/var/lib/binance-mcp/requests"))
    try:
        result = run_cli(
            list(sys.argv[1:] if argv is None else argv),
            handlers=build_default_handlers(),
            request_root=request_root,
        )
    except BoundaryError as exc:
        print(json.dumps({"status": "DENY", "reason": str(exc)}, separators=(",", ":")), file=sys.stderr)
        return 2
    except Exception as exc:
        print(json.dumps({"status": "ERROR", "reason": type(exc).__name__}, separators=(",", ":")), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
