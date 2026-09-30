#!/usr/bin/env python3
"""Collect a bounded snapshot of public research data.

This command performs read-only HTTP GET requests. It does not place orders or access accounts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from edge_lab.providers import BinancePublicClient, CoinMetricsCommunityClient


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spot-symbol", default="BTCUSDT")
    parser.add_argument("--coinm-symbol", default="BTCUSD_PERP")
    parser.add_argument("--coinm-pair", default="BTCUSD")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--start-ms", type=int, required=True)
    parser.add_argument("--end-ms", type=int, required=True)
    parser.add_argument("--onchain-asset", default="btc")
    parser.add_argument("--onchain-start", required=True)
    parser.add_argument("--onchain-end", required=True)
    parser.add_argument(
        "--onchain-metrics",
        default="AdrActCnt,TxCnt,FeeTotNtv",
        help="Coin Metrics Community metrics; availability varies by asset.",
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.end_ms <= args.start_ms:
        raise ValueError("end-ms must be greater than start-ms")

    binance = BinancePublicClient()
    coinmetrics = CoinMetricsCommunityClient()

    payload = {
        "schema_version": "1.0.0",
        "mode": "RESEARCH_ONLY",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "request": {
            "spot_symbol": args.spot_symbol,
            "coinm_symbol": args.coinm_symbol,
            "coinm_pair": args.coinm_pair,
            "interval": args.interval,
            "start_ms": args.start_ms,
            "end_ms": args.end_ms,
            "onchain_asset": args.onchain_asset,
            "onchain_start": args.onchain_start,
            "onchain_end": args.onchain_end,
            "onchain_metrics": args.onchain_metrics.split(","),
        },
        "data": {
            "spot_klines": binance.spot_klines(
                symbol=args.spot_symbol,
                interval=args.interval,
                start_time=args.start_ms,
                end_time=args.end_ms,
                limit=1000,
            ),
            "coinm_funding": binance.coinm_funding_rate(
                symbol=args.coinm_symbol,
                start_time=args.start_ms,
                end_time=args.end_ms,
                limit=1000,
            ),
            "coinm_open_interest": binance.coinm_open_interest_history(
                pair=args.coinm_pair,
                period=args.interval,
                start_time=args.start_ms,
                end_time=args.end_ms,
                limit=500,
            ),
            "coinm_taker_buy_sell": binance.coinm_taker_buy_sell(
                pair=args.coinm_pair,
                period=args.interval,
                start_time=args.start_ms,
                end_time=args.end_ms,
                limit=500,
            ),
            "coinm_basis": binance.coinm_basis(
                pair=args.coinm_pair,
                period=args.interval,
                start_time=args.start_ms,
                end_time=args.end_ms,
                limit=500,
            ),
            "onchain_asset_metrics": coinmetrics.asset_metrics(
                assets=[args.onchain_asset],
                metrics=[m for m in args.onchain_metrics.split(",") if m],
                start_time=args.onchain_start,
                end_time=args.onchain_end,
                frequency="1d",
            ),
        },
        "safety": {
            "credentials_used": False,
            "account_accessed": False,
            "orders_placed": False,
            "holdout_accessed": False,
            "live_authorized": False,
        },
    }
    digest = hashlib.sha256(canonical_bytes(payload["data"])).hexdigest()
    payload["data_sha256"] = digest

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_bytes(payload))
    print(f"PUBLIC_DATA_SNAPSHOT={output}")
    print(f"DATA_SHA256={digest}")
    print("LIVE_AUTHORIZED=false")


if __name__ == "__main__":
    main()
