"""Governed Binance Spot order submission.

TESTNET is the only environment enabled by default. Network ambiguity never
triggers an automatic retry because the exchange may already have accepted the
order.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .binance_auth import BinanceSigner
from .canonical import sha256_json
from .contracts import OrderRecord, OrderState, TradeIntent


Environment = Literal["TESTNET", "LIVE_PILOT", "LIMITED_LIVE"]
TESTNET_BASE_URL = "https://testnet.binance.vision"
LIVE_BASE_URL = "https://api.binance.com"


class ExecutionNotAuthorized(RuntimeError):
    pass


class OrderRejectedError(RuntimeError):
    pass


class AmbiguousSubmissionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExchangeSubmission:
    client_order_id: str
    exchange_order_id: str
    status: str
    response_sha256: str


@dataclass
class BinanceOrderClient:
    api_key: str = field(repr=False)
    api_secret: str = field(repr=False)
    environment: Environment = "TESTNET"
    intent_lookup: Callable[[str], TradeIntent | None] = field(repr=False, default=lambda _: None)
    timeout: float = 15.0
    recv_window_ms: int = 5000
    clock_ms: Callable[[], int] = field(default=lambda: 0, repr=False)
    live_enabled: bool = False

    def __post_init__(self) -> None:
        if not self.api_key or "\n" in self.api_key or "\r" in self.api_key:
            raise ValueError("api_key must be one nonempty line")
        if not self.api_secret or "\n" in self.api_secret or "\r" in self.api_secret:
            raise ValueError("api_secret must be one nonempty line")
        if self.environment not in {"TESTNET", "LIVE_PILOT", "LIMITED_LIVE"}:
            raise ValueError("unsupported Binance order environment")
        if self.environment != "TESTNET" and not self.live_enabled:
            raise ExecutionNotAuthorized("live Binance order endpoint is disabled")

    @property
    def base_url(self) -> str:
        return TESTNET_BASE_URL if self.environment == "TESTNET" else LIVE_BASE_URL

    def _intent_for(self, order: OrderRecord) -> TradeIntent:
        if order.state != OrderState.HUMAN_APPROVED or not order.authorization_id:
            raise ExecutionNotAuthorized("order must be HUMAN_APPROVED")
        intent = self.intent_lookup(order.intent_sha256)
        if intent is None or intent.intent_sha256() != order.intent_sha256:
            raise ExecutionNotAuthorized("approved order intent is unavailable or mismatched")
        if intent.environment != self.environment:
            raise ExecutionNotAuthorized("order/client environment mismatch")
        return intent

    def _signed_order_params(self, order: OrderRecord, intent: TradeIntent) -> dict[str, str]:
        params: dict[str, str] = {
            "symbol": intent.symbol,
            "side": intent.side,
            "type": intent.order_type,
            "newClientOrderId": order.client_order_id,
            "newOrderRespType": "FULL",
        }
        if intent.quantity is not None:
            params["quantity"] = intent.quantity
        if intent.quote_quantity is not None:
            params["quoteOrderQty"] = intent.quote_quantity
        if intent.price is not None:
            params["price"] = intent.price
        if intent.stop_price is not None:
            params["stopPrice"] = intent.stop_price
        if intent.time_in_force is not None:
            params["timeInForce"] = intent.time_in_force
        return params

    def submit_approved(self, order: OrderRecord) -> ExchangeSubmission:
        intent = self._intent_for(order)
        parsed = urlparse(self.base_url)
        expected_host = "testnet.binance.vision" if self.environment == "TESTNET" else "api.binance.com"
        if parsed.scheme != "https" or parsed.hostname != expected_host:
            raise ExecutionNotAuthorized("Binance order host is not allowlisted")

        signer = BinanceSigner(api_key=self.api_key, api_secret=self.api_secret)
        signed = signer.sign(
            "POST",
            "/api/v3/order",
            self._signed_order_params(order, intent),
            timestamp_ms=int(self.clock_ms()),
            recv_window_ms=self.recv_window_ms,
        )
        url = f"{self.base_url}{signed.path}?{signed.query_string}&signature={signed.signature}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "X-MBX-APIKEY": self.api_key,
                "User-Agent": "institutional-trading-bot-status-binance-mcp/1.0",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                if response.status >= 500:
                    raise AmbiguousSubmissionError(f"Binance HTTP {response.status}")
                if response.status >= 400:
                    raise OrderRejectedError(f"Binance HTTP {response.status}")
        except HTTPError as exc:
            if exc.code >= 500:
                raise AmbiguousSubmissionError(f"Binance HTTP {exc.code}") from exc
            raise OrderRejectedError(f"Binance HTTP {exc.code}") from exc
        except (TimeoutError, URLError, OSError) as exc:
            raise AmbiguousSubmissionError("Binance order outcome is ambiguous") from exc

        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise AmbiguousSubmissionError("Binance order response is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise AmbiguousSubmissionError("unexpected Binance order response schema")
        if payload.get("clientOrderId") != order.client_order_id:
            raise AmbiguousSubmissionError("Binance client order id mismatch")
        exchange_order_id = payload.get("orderId")
        status = payload.get("status")
        if exchange_order_id is None or not isinstance(status, str) or not status:
            raise AmbiguousSubmissionError("incomplete Binance order acknowledgement")

        return ExchangeSubmission(
            client_order_id=order.client_order_id,
            exchange_order_id=str(exchange_order_id),
            status=status,
            response_sha256=sha256_json(payload),
        )
