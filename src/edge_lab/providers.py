"""Read-only public market/on-chain data adapters.

No authentication, signing, order placement, withdrawals or account endpoints exist here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


ALLOWED_HOSTS = {
    "api.binance.com",
    "dapi.binance.com",
    "community-api.coinmetrics.io",
}


class ProviderError(RuntimeError):
    pass


def _get_json(base_url: str, path: str, params: dict[str, Any] | None = None, *, timeout: float = 15.0) -> Any:
    query = urlencode({k: v for k, v in (params or {}).items() if v is not None})
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    if query:
        url = f"{url}?{query}"

    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ProviderError(f"host not allowlisted: {parsed.hostname!r}")

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "institutional-trading-bot-status-edge-lab/1.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise ProviderError(f"HTTP {response.status} for {url}")
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        if isinstance(exc, ProviderError):
            raise
        raise ProviderError(f"GET failed for {url}: {exc}") from exc


@dataclass(frozen=True)
class BinancePublicClient:
    spot_base_url: str = "https://api.binance.com"
    coinm_base_url: str = "https://dapi.binance.com"
    timeout: float = 15.0

    def spot_klines(
        self,
        *,
        symbol: str,
        interval: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 1000,
    ) -> list[Any]:
        return _get_json(
            self.spot_base_url,
            "/api/v3/klines",
            {
                "symbol": symbol,
                "interval": interval,
                "startTime": start_time,
                "endTime": end_time,
                "limit": limit,
            },
            timeout=self.timeout,
        )

    def coinm_funding_rate(
        self,
        *,
        symbol: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        return _get_json(
            self.coinm_base_url,
            "/dapi/v1/fundingRate",
            {"symbol": symbol, "startTime": start_time, "endTime": end_time, "limit": limit},
            timeout=self.timeout,
        )

    def coinm_open_interest_history(
        self,
        *,
        pair: str,
        period: str,
        contract_type: str = "PERPETUAL",
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        return _get_json(
            self.coinm_base_url,
            "/futures/data/openInterestHist",
            {
                "pair": pair,
                "contractType": contract_type,
                "period": period,
                "startTime": start_time,
                "endTime": end_time,
                "limit": limit,
            },
            timeout=self.timeout,
        )

    def coinm_taker_buy_sell(
        self,
        *,
        pair: str,
        period: str,
        contract_type: str = "PERPETUAL",
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        return _get_json(
            self.coinm_base_url,
            "/futures/data/takerBuySellVol",
            {
                "pair": pair,
                "contractType": contract_type,
                "period": period,
                "startTime": start_time,
                "endTime": end_time,
                "limit": limit,
            },
            timeout=self.timeout,
        )

    def coinm_basis(
        self,
        *,
        pair: str,
        period: str,
        contract_type: str = "PERPETUAL",
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        return _get_json(
            self.coinm_base_url,
            "/futures/data/basis",
            {
                "pair": pair,
                "contractType": contract_type,
                "period": period,
                "startTime": start_time,
                "endTime": end_time,
                "limit": limit,
            },
            timeout=self.timeout,
        )

    def coinm_book_ticker(self, *, pair: str | None = None, symbol: str | None = None) -> Any:
        if pair and symbol:
            raise ProviderError("provide pair or symbol, not both")
        return _get_json(
            self.coinm_base_url,
            "/dapi/v1/ticker/bookTicker",
            {"pair": pair, "symbol": symbol},
            timeout=self.timeout,
        )


@dataclass(frozen=True)
class CoinMetricsCommunityClient:
    base_url: str = "https://community-api.coinmetrics.io/v4"
    timeout: float = 15.0
    max_pages: int = 50

    def asset_metrics(
        self,
        *,
        assets: Iterable[str],
        metrics: Iterable[str],
        start_time: str,
        end_time: str,
        frequency: str = "1d",
        page_size: int = 10000,
    ) -> list[dict[str, Any]]:
        params = {
            "assets": ",".join(assets),
            "metrics": ",".join(metrics),
            "start_time": start_time,
            "end_time": end_time,
            "frequency": frequency,
            "page_size": page_size,
            "paging_from": "start",
        }
        payload = _get_json(self.base_url, "/timeseries/asset-metrics", params, timeout=self.timeout)
        rows: list[dict[str, Any]] = []
        for _ in range(self.max_pages):
            rows.extend(payload.get("data", []))
            next_url = payload.get("next_page_url")
            if not next_url:
                return rows
            parsed = urlparse(next_url)
            if parsed.scheme != "https" or parsed.hostname != "community-api.coinmetrics.io":
                raise ProviderError("Coin Metrics pagination left allowlisted host")
            request = Request(
                next_url,
                headers={"Accept": "application/json", "User-Agent": "institutional-trading-bot-status-edge-lab/1.0"},
                method="GET",
            )
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except Exception as exc:
                raise ProviderError(f"Coin Metrics pagination failed: {exc}") from exc
        raise ProviderError("Coin Metrics pagination exceeded max_pages")
