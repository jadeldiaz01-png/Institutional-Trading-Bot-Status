"""Binance signed-request primitives with no logging of credentials."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode


@dataclass(frozen=True)
class SignedRequest:
    method: str
    path: str
    query_string: str
    signature: str


@dataclass(frozen=True)
class BinanceSigner:
    api_key: str = field(repr=False)
    api_secret: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.api_key or "\n" in self.api_key or "\r" in self.api_key:
            raise ValueError("api_key must be one nonempty line")
        if not self.api_secret or "\n" in self.api_secret or "\r" in self.api_secret:
            raise ValueError("api_secret must be one nonempty line")

    def sign(
        self,
        method: str,
        path: str,
        params: dict[str, Any],
        *,
        timestamp_ms: int,
        recv_window_ms: int,
    ) -> SignedRequest:
        normalized_method = method.upper()
        if normalized_method not in {"GET", "POST", "DELETE"}:
            raise ValueError("unsupported Binance signed method")
        if not path.startswith("/"):
            raise ValueError("Binance path must be absolute")
        if timestamp_ms < 0:
            raise ValueError("timestamp_ms must be nonnegative")
        if not 1 <= recv_window_ms <= 60000:
            raise ValueError("recv_window_ms must be between 1 and 60000")
        if {"timestamp", "recvWindow", "signature"} & set(params):
            raise ValueError("reserved Binance signing parameter supplied")

        signed_params = dict(params)
        signed_params["timestamp"] = timestamp_ms
        signed_params["recvWindow"] = recv_window_ms
        query_string = urlencode(sorted(signed_params.items()))
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return SignedRequest(
            method=normalized_method,
            path=path,
            query_string=query_string,
            signature=signature,
        )
