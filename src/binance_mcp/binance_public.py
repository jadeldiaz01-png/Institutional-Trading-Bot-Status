"""Read-only official Binance Spot market-data adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


ALLOWED_HOSTS = {"api.binance.com"}


class ProviderError(RuntimeError):
    pass


def _require_symbol(symbol: str) -> str:
    value = symbol.strip().upper()
    if not value or len(value) > 32 or not value.isalnum():
        raise ProviderError("invalid symbol")
    return value


@dataclass(frozen=True)
class SymbolFilters:
    symbol: str
    status: str
    order_types: tuple[str, ...]
    tick_size: str
    step_size: str
    min_qty: str
    max_qty: str
    min_notional: str | None
    max_notional: str | None = None


@dataclass(frozen=True)
class BinancePublicClient:
    base_url: str = "https://api.binance.com"
    timeout: float = 15.0

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        parsed_base = urlparse(self.base_url)
        if parsed_base.scheme != "https" or parsed_base.hostname not in ALLOWED_HOSTS:
            raise ProviderError("Binance base URL is not allowlisted")
        query = urlencode({key: value for key, value in (params or {}).items() if value is not None})
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        if query:
            url = f"{url}?{query}"
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
            raise ProviderError("Binance request URL is not allowlisted")

        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "institutional-trading-bot-status-binance-mcp/1.0",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise ProviderError(f"Binance HTTP {response.status}")
                raw = response.read().decode("utf-8")
        except ProviderError:
            raise
        except HTTPError as exc:
            raise ProviderError(f"Binance HTTP {exc.code}") from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise ProviderError("Binance public request failed") from exc

        try:
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderError("Binance response is not valid JSON") from exc

    def exchange_info(self, symbol: str | None = None) -> dict[str, Any]:
        params = {"symbol": _require_symbol(symbol)} if symbol is not None else None
        payload = self._get_json("/api/v3/exchangeInfo", params)
        if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
            raise ProviderError("unexpected Binance exchangeInfo schema")
        return payload

    def ticker(self, symbol: str) -> dict[str, Any]:
        value = _require_symbol(symbol)
        payload = self._get_json("/api/v3/ticker/price", {"symbol": value})
        if not isinstance(payload, dict) or payload.get("symbol") != value or "price" not in payload:
            raise ProviderError("unexpected Binance ticker schema")
        return payload

    def klines(self, symbol: str, interval: str, limit: int) -> list[Any]:
        value = _require_symbol(symbol)
        if not interval.strip() or not 1 <= limit <= 1000:
            raise ProviderError("invalid kline request")
        payload = self._get_json(
            "/api/v3/klines",
            {"symbol": value, "interval": interval, "limit": limit},
        )
        if not isinstance(payload, list) or any(not isinstance(row, list) for row in payload):
            raise ProviderError("unexpected Binance klines schema")
        return payload

    def order_book(self, symbol: str, limit: int) -> dict[str, Any]:
        value = _require_symbol(symbol)
        if not 1 <= limit <= 5000:
            raise ProviderError("invalid order-book limit")
        payload = self._get_json("/api/v3/depth", {"symbol": value, "limit": limit})
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("bids"), list)
            or not isinstance(payload.get("asks"), list)
        ):
            raise ProviderError("unexpected Binance order-book schema")
        return payload

    def recent_trades(self, symbol: str, limit: int) -> list[dict[str, Any]]:
        value = _require_symbol(symbol)
        if not 1 <= limit <= 1000:
            raise ProviderError("invalid recent-trades limit")
        payload = self._get_json("/api/v3/trades", {"symbol": value, "limit": limit})
        if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
            raise ProviderError("unexpected Binance recent-trades schema")
        return payload

    def symbol_filters(self, symbol: str) -> SymbolFilters:
        value = _require_symbol(symbol)
        payload = self.exchange_info(value)
        item = next(
            (
                row
                for row in payload["symbols"]
                if isinstance(row, dict) and row.get("symbol") == value
            ),
            None,
        )
        if item is None:
            raise ProviderError("unknown Binance symbol")

        filters_raw = item.get("filters")
        if not isinstance(filters_raw, list):
            raise ProviderError("unexpected Binance symbol filter schema")
        by_type = {
            row.get("filterType"): row
            for row in filters_raw
            if isinstance(row, dict) and isinstance(row.get("filterType"), str)
        }
        price_filter = by_type.get("PRICE_FILTER")
        lot_filter = by_type.get("LOT_SIZE")
        notional_filter = by_type.get("NOTIONAL") or by_type.get("MIN_NOTIONAL")
        if not isinstance(price_filter, dict) or not isinstance(lot_filter, dict):
            raise ProviderError("required Binance symbol filters are missing")

        required_price = price_filter.get("tickSize")
        required_lot = (lot_filter.get("stepSize"), lot_filter.get("minQty"), lot_filter.get("maxQty"))
        if not isinstance(required_price, str) or any(not isinstance(value_, str) for value_ in required_lot):
            raise ProviderError("invalid Binance symbol filter values")

        min_notional = None
        max_notional = None
        if isinstance(notional_filter, dict):
            raw_min = notional_filter.get("minNotional")
            raw_max = notional_filter.get("maxNotional")
            min_notional = raw_min if isinstance(raw_min, str) else None
            max_notional = raw_max if isinstance(raw_max, str) else None

        order_types = item.get("orderTypes")
        if not isinstance(order_types, list) or any(not isinstance(value_, str) for value_ in order_types):
            raise ProviderError("unexpected Binance orderTypes schema")

        return SymbolFilters(
            symbol=value,
            status=str(item.get("status", "")),
            order_types=tuple(order_types),
            tick_size=required_price,
            step_size=required_lot[0],
            min_qty=required_lot[1],
            max_qty=required_lot[2],
            min_notional=min_notional,
            max_notional=max_notional,
        )
