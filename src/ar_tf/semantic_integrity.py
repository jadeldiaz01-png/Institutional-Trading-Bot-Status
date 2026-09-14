from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .historical_dataset import _download_verified_zip


def semantic_anomalies(frame: pd.DataFrame) -> list[dict[str, Any]]:
    required = ["timestamp", "open", "high", "low", "close", "volume", "quote_volume", "trade_count"]
    missing = [c for c in required if c not in frame.columns]
    if missing:
        return [{"type": "SCHEMA_MISSING", "columns": missing}]
    x = frame.copy()
    for c in required[1:]:
        x[c] = pd.to_numeric(x[c], errors="coerce")
    out: list[dict[str, Any]] = []
    for i, row in x.iterrows():
        ts = str(frame.loc[i, "timestamp"])
        if row[required[1:]].isna().any():
            out.append({"type": "NON_NUMERIC", "timestamp": ts}); continue
        if min(row["open"], row["high"], row["low"], row["close"]) <= 0:
            out.append({"type": "NON_POSITIVE_PRICE", "timestamp": ts})
        if row["high"] < max(row["open"], row["close"], row["low"]):
            out.append({"type": "HIGH_INVARIANT", "timestamp": ts})
        if row["low"] > min(row["open"], row["close"], row["high"]):
            out.append({"type": "LOW_INVARIANT", "timestamp": ts})
        if row["volume"] < 0 or row["quote_volume"] < 0 or row["trade_count"] < 0:
            out.append({"type": "NEGATIVE_ACTIVITY", "timestamp": ts})
    return out


def reconstruct_day_from_1m(symbol: str, day: pd.Timestamp, timeout: int = 60) -> tuple[dict[str, Any], dict[str, Any]]:
    day = pd.Timestamp(day)
    day = day.tz_localize("UTC") if day.tzinfo is None else day.tz_convert("UTC")
    day = day.normalize()
    key = f"data/spot/daily/klines/{symbol}/1m/{symbol}-1m-{day.strftime('%Y-%m-%d')}.zip"
    minute, digest = _download_verified_zip(key, timeout=timeout)
    if minute.empty:
        raise ValueError(f"no 1m rows for {symbol} {day.date()}")
    row = {
        "timestamp": day.isoformat(),
        "open": float(minute.iloc[0]["open"]),
        "high": float(minute["high"].max()),
        "low": float(minute["low"].min()),
        "close": float(minute.iloc[-1]["close"]),
        "volume": float(minute["volume"].sum()),
        "quote_volume": float(minute["quote_volume"].sum()),
        "trade_count": int(minute["trade_count"].sum()),
    }
    if semantic_anomalies(pd.DataFrame([row])):
        raise ValueError(f"reconstructed row invalid for {symbol} {day.date()}")
    return row, {"key": key, "sha256": digest, "authority": "BINANCE_VISION_CHECKSUM_VERIFIED_1M"}


def scan_dataset(dataset_dir: str | Path) -> dict[str, Any]:
    root = Path(dataset_dir)
    anomalies=[]
    for path in sorted((root / "market").glob("*.csv")):
        frame=pd.read_csv(path)
        for item in semantic_anomalies(frame):
            anomalies.append({"market_file": path.name, **item})
    return {"anomaly_count": len(anomalies), "anomalies": anomalies}


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
