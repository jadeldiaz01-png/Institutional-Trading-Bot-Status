from __future__ import annotations

import csv
import hashlib
import io
import json
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

BINANCE_VISION_BASE = "https://data.binance.vision/data/spot/monthly/klines"
KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trade_count", "taker_buy_base", "taker_buy_quote", "ignore",
]


@dataclass(frozen=True)
class SymbolLifecycle:
    symbol: str
    listed_at: pd.Timestamp
    delisted_at: pd.Timestamp | None = None

    def active_on(self, ts: pd.Timestamp) -> bool:
        t = pd.Timestamp(ts)
        if t.tzinfo is None:
            t = t.tz_localize("UTC")
        else:
            t = t.tz_convert("UTC")
        return t >= self.listed_at and (self.delisted_at is None or t < self.delisted_at)


def load_lifecycle_csv(path: str | Path) -> dict[str, SymbolLifecycle]:
    rows: dict[str, SymbolLifecycle] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            listed = pd.Timestamp(row["listed_at"])
            listed = listed.tz_localize("UTC") if listed.tzinfo is None else listed.tz_convert("UTC")
            raw_delisted = (row.get("delisted_at") or "").strip()
            delisted = pd.Timestamp(raw_delisted) if raw_delisted else None
            if delisted is not None:
                delisted = delisted.tz_localize("UTC") if delisted.tzinfo is None else delisted.tz_convert("UTC")
            rows[row["symbol"]] = SymbolLifecycle(row["symbol"], listed, delisted)
    if not rows:
        raise ValueError("historical universe metadata is empty")
    return rows


def active_universe(lifecycles: dict[str, SymbolLifecycle], ts: pd.Timestamp) -> set[str]:
    return {s for s, lifecycle in lifecycles.items() if lifecycle.active_on(ts)}


def binance_month_url(symbol: str, interval: str, year: int, month: int) -> str:
    return f"{BINANCE_VISION_BASE}/{symbol}/{interval}/{symbol}-{interval}-{year:04d}-{month:02d}.zip"


def download_month(symbol: str, interval: str, year: int, month: int, timeout: int = 30) -> pd.DataFrame:
    url = binance_month_url(symbol, interval, year, month)
    req = urllib.request.Request(url, headers={"User-Agent": "AR-TF-research/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return pd.DataFrame(columns=KLINE_COLUMNS)
        raise
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        if len(names) != 1:
            raise ValueError(f"unexpected Binance archive contents for {symbol}: {names}")
        with archive.open(names[0]) as raw:
            frame = pd.read_csv(raw, header=None, names=KLINE_COLUMNS)
    frame["timestamp"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    frame = frame.set_index("timestamp").sort_index()
    for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["trade_count"] = pd.to_numeric(frame["trade_count"], errors="coerce").fillna(0).astype("int64")
    return frame[["open", "high", "low", "close", "volume", "quote_volume", "trade_count"]]


def dataset_digest(frames: dict[str, pd.DataFrame]) -> str:
    h = hashlib.sha256()
    for symbol in sorted(frames):
        h.update(symbol.encode())
        canonical = frames[symbol].sort_index().to_csv(index=True, date_format="%Y-%m-%dT%H:%M:%S.%f%z").encode()
        h.update(canonical)
    return h.hexdigest()


def build_manifest(frames: dict[str, pd.DataFrame], source: str, lifecycle_source: str) -> dict:
    if not frames:
        raise ValueError("cannot certify an empty dataset")
    gaps = []
    for symbol, frame in frames.items():
        if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
            raise ValueError(f"non point-in-time ordering for {symbol}")
        if frame.empty:
            gaps.append({"symbol": symbol, "reason": "NO_DATA"})
    return {
        "dataset_id": "ar-tf-binance-spot-history",
        "version": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "source": source,
        "license": None,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "timezone": "UTC",
        "symbols": sorted(frames),
        "fields": ["open", "high", "low", "close", "volume", "quote_volume", "trade_count"],
        "sha256": dataset_digest(frames),
        "point_in_time": True,
        "survivorship_bias_control": f"symbol lifecycle metadata required from {lifecycle_source}; current exchange listings alone are forbidden",
        "corporate_or_token_events": [],
        "known_gaps": gaps,
    }


def write_manifest(manifest: dict, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
