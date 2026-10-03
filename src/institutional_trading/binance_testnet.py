from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

import httpx

from .domain import OrderIntent


TESTNET_BASE_URL = "https://testnet.binance.vision"


class BrokerTimeoutUnknown(RuntimeError):
    """Submission outcome is unknown; caller must reconcile before retrying."""


class BrokerRejected(RuntimeError):
    pass


@dataclass(slots=True)
class SubmittedOrder:
    broker_order_id: str
    client_order_id: str
    status: str
    raw: dict[str, Any]


class BinanceSpotTestnetAdapter:
    """TESTNET-only adapter.

    Secrets are injected at runtime. This class refuses non-testnet base URLs and never
    exposes withdrawal endpoints. POST timeouts are represented as UNKNOWN, not failure.
    """

    def __init__(self, api_key: str, api_secret: str, *, base_url: str = TESTNET_BASE_URL,
                 timeout_seconds: float = 5.0) -> None:
        if base_url.rstrip("/") not in {
            "https://testnet.binance.vision",
            "https://api1.testnet.binance.vision",
        }:
            raise ValueError("adapter is hard-limited to Binance Spot Testnet")
        if not api_key or not api_secret:
            raise ValueError("TESTNET credentials must be injected at runtime")
        self._api_key = api_key
        self._secret = api_secret.encode()
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_seconds)

    def _signed(self, params: dict[str, Any]) -> dict[str, Any]:
        material = {**params, "timestamp": int(time.time() * 1000), "recvWindow": 5000}
        query = urlencode(material)
        material["signature"] = hmac.new(self._secret, query.encode(), hashlib.sha256).hexdigest()
        return material

    def ping(self) -> bool:
        response = self._client.get("/api/v3/ping")
        response.raise_for_status()
        return response.json() == {}

    def submit(self, intent: OrderIntent) -> SubmittedOrder:
        if intent.environment.value != "TESTNET":
            raise ValueError("BinanceSpotTestnetAdapter accepts TESTNET intents only")
        params: dict[str, Any] = {
            "symbol": intent.symbol,
            "side": intent.side,
            "type": intent.order_type,
            "quantity": format(intent.quantity, "f"),
            "newClientOrderId": intent.client_order_id,
            "newOrderRespType": "RESULT",
        }
        if intent.order_type == "LIMIT":
            if intent.limit_price is None:
                raise ValueError("LIMIT requires limit_price")
            params.update({"timeInForce": "GTC", "price": format(intent.limit_price, "f")})
        try:
            response = self._client.post(
                "/api/v3/order",
                headers={"X-MBX-APIKEY": self._api_key},
                data=self._signed(params),
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise BrokerTimeoutUnknown("submission outcome unknown; reconcile by client_order_id") from exc
        if response.status_code >= 400:
            try:
                payload = response.json()
            except ValueError:
                payload = {"status_code": response.status_code}
            raise BrokerRejected(str(payload))
        payload = response.json()
        return SubmittedOrder(
            broker_order_id=str(payload["orderId"]),
            client_order_id=str(payload.get("clientOrderId", intent.client_order_id)),
            status=str(payload["status"]),
            raw=payload,
        )

    def query_by_client_order_id(self, symbol: str, client_order_id: str) -> dict[str, Any] | None:
        params = self._signed({"symbol": symbol, "origClientOrderId": client_order_id})
        try:
            response = self._client.get(
                "/api/v3/order",
                headers={"X-MBX-APIKEY": self._api_key},
                params=params,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise BrokerTimeoutUnknown("reconciliation query timed out") from exc
        if response.status_code == 400:
            payload = response.json()
            if payload.get("code") == -2013:
                return None
        response.raise_for_status()
        return response.json()
