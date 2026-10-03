"""Authenticated Binance account-read adapter and permission policy."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .binance_auth import BinanceSigner
from .canonical import sha256_json
from .contracts import BinancePermissions, RiskDecision

ALLOWED_HOSTS = {"api.binance.com"}


def _read_single_line(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"credential file missing: {path}")
    raw = path.read_text(encoding="utf-8")
    value = raw.rstrip("\r\n")
    if not value or "\n" in value or "\r" in value:
        raise ValueError("credential must contain exactly one nonempty line")
    return value


@dataclass(frozen=True)
class PermissionPolicy:
    required_true: tuple[str, ...]
    required_false: tuple[str, ...]

    @classmethod
    def read_only(cls) -> "PermissionPolicy":
        return cls(
            required_true=("ipRestrict", "enableReading"),
            required_false=(
                "enableSpotAndMarginTrading",
                "enableWithdrawals",
                "enableInternalTransfer",
                "permitsUniversalTransfer",
                "enableMargin",
                "enableFutures",
                "enableVanillaOptions",
                "enablePortfolioMarginTrading",
                "enableFixApiTrade",
            ),
        )

    def evaluate_payload(self, payload: dict[str, Any]) -> RiskDecision:
        reasons: list[str] = []
        for key in self.required_true:
            if payload.get(key) is not True:
                reasons.append(f"{key}=required_true")
        for key in self.required_false:
            if key not in payload:
                reasons.append(f"{key}=missing")
            elif payload.get(key) is not False:
                reasons.append(f"{key}=forbidden_true")
        return RiskDecision(
            allowed=not reasons,
            reasons=tuple(reasons),
            snapshot_sha256=sha256_json(payload),
        )


@dataclass
class BinanceAccountClient:
    _api_key: str = field(repr=False)
    _api_secret: str = field(repr=False)
    base_url: str = "https://api.binance.com"
    timeout: float = 15.0
    recv_window_ms: int = 5000
    clock_ms: Callable[[], int] = field(
        default_factory=lambda: lambda: int(time.time() * 1000),
        repr=False,
    )

    @classmethod
    def from_credential_files(
        cls,
        *,
        api_key_file: Path,
        api_secret_file: Path,
        base_url: str = "https://api.binance.com",
        timeout: float = 15.0,
        recv_window_ms: int = 5000,
        clock_ms: Callable[[], int] | None = None,
    ) -> "BinanceAccountClient":
        return cls(
            _api_key=_read_single_line(api_key_file),
            _api_secret=_read_single_line(api_secret_file),
            base_url=base_url,
            timeout=timeout,
            recv_window_ms=recv_window_ms,
            clock_ms=clock_ms or (lambda: int(time.time() * 1000)),
        )

    def _signed_get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
            raise ValueError("Binance account base URL is not allowlisted")
        signer = BinanceSigner(api_key=self._api_key, api_secret=self._api_secret)
        signed = signer.sign(
            "GET",
            path,
            params or {},
            timestamp_ms=int(self.clock_ms()),
            recv_window_ms=self.recv_window_ms,
        )
        url = (
            f"{self.base_url.rstrip('/')}{signed.path}"
            f"?{signed.query_string}&signature={signed.signature}"
        )
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "X-MBX-APIKEY": self._api_key,
                "User-Agent": "institutional-trading-bot-status-binance-mcp/1.0",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise RuntimeError(f"Binance HTTP {response.status}")
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            raise RuntimeError(f"Binance HTTP {exc.code}") from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise RuntimeError("Binance account request failed") from exc
        try:
            return json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError("Binance account response is not valid JSON") from exc

    def account_status(self) -> dict[str, Any]:
        payload = self._signed_get("/sapi/v1/account/status")
        if not isinstance(payload, dict):
            raise RuntimeError("unexpected Binance account status schema")
        return payload

    def permissions_payload(self) -> dict[str, Any]:
        payload = self._signed_get("/sapi/v1/account/apiRestrictions")
        if not isinstance(payload, dict):
            raise RuntimeError("unexpected Binance permission schema")
        return payload

    def permissions(self) -> BinancePermissions:
        payload = self.permissions_payload()
        return BinancePermissions(
            read=payload.get("enableReading") is True,
            spot_trade=payload.get("enableSpotAndMarginTrading") is True,
            withdrawals=payload.get("enableWithdrawals") is True,
            internal_transfer=payload.get("enableInternalTransfer") is True,
            universal_transfer=payload.get("permitsUniversalTransfer") is True,
            margin=payload.get("enableMargin") is True,
            futures=payload.get("enableFutures") is True,
        )

    def balances(self) -> list[dict[str, Any]]:
        payload = self._signed_get("/api/v3/account", {"omitZeroBalances": "false"})
        balances = payload.get("balances") if isinstance(payload, dict) else None
        if not isinstance(balances, list) or any(not isinstance(row, dict) for row in balances):
            raise RuntimeError("unexpected Binance balances schema")
        return balances

    def open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        params = {"symbol": symbol} if symbol else {}
        payload = self._signed_get("/api/v3/openOrders", params)
        if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
            raise RuntimeError("unexpected Binance open-orders schema")
        return payload

    def order_history(self, symbol: str, limit: int = 500) -> list[dict[str, Any]]:
        payload = self._signed_get("/api/v3/allOrders", {"symbol": symbol, "limit": limit})
        if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
            raise RuntimeError("unexpected Binance order-history schema")
        return payload

    def trade_history(self, symbol: str, limit: int = 500) -> list[dict[str, Any]]:
        payload = self._signed_get("/api/v3/myTrades", {"symbol": symbol, "limit": limit})
        if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
            raise RuntimeError("unexpected Binance trade-history schema")
        return payload
