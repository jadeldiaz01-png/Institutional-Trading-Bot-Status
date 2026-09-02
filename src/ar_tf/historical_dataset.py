from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from pathlib import Path

import pandas as pd

from .evidence_acquisition import VISION_BASE, canonical_sha256
from .lifecycle_verifier import _timestamp_unit, file_sha256

KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trade_count", "taker_buy_base", "taker_buy_quote", "ignore",
]


@dataclass(frozen=True)
class ArchiveFetch:
    symbol: str
    month: str
    key: str
    sha256: str
    rows: int
    first_timestamp: str
    last_timestamp: str


def _read_with_retry(url: str, *, timeout: int = 60, attempts: int = 4) -> bytes:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AR-TF-dataset/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if isinstance(exc, urllib.error.HTTPError) and 400 <= exc.code < 500 and exc.code != 429:
                raise
            if attempt + 1 < attempts:
                time.sleep(min(8.0, 0.5 * (2 ** attempt)))
    raise RuntimeError(f"archive fetch failed after retries: {url}: {last}")


def _verify_checksum(payload: bytes, checksum_payload: bytes, expected_filename: str) -> str:
    text = checksum_payload.decode("utf-8").strip().split()
    if not text or len(text[0]) != 64:
        raise ValueError(f"invalid checksum for {expected_filename}")
    expected = text[0].lower()
    actual = hashlib.sha256(payload).hexdigest()
    if expected != actual:
        raise ValueError(f"checksum mismatch for {expected_filename}")
    return actual


def parse_monthly_archive(key: str, *, timeout: int = 60) -> tuple[pd.DataFrame, str]:
    url = f"{VISION_BASE}/{key}"
    payload = _read_with_retry(url, timeout=timeout)
    checksum_payload = _read_with_retry(url + ".CHECKSUM", timeout=timeout)
    filename = key.rsplit("/", 1)[-1]
    digest = _verify_checksum(payload, checksum_payload, filename)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        if len(names) != 1:
            raise ValueError(f"unexpected archive contents: {key}: {names}")
        rows = list(csv.reader(io.TextIOWrapper(archive.open(names[0]), encoding="utf-8")))
    if not rows:
        raise ValueError(f"empty archive: {key}")
    frame = pd.DataFrame(rows, columns=KLINE_COLUMNS)
    open_values = pd.to_numeric(frame["open_time"], errors="raise").astype("int64")
    units = open_values.map(_timestamp_unit)
    # Binance's archive unit is consistent within a file. Fail closed otherwise.
    if units.nunique() != 1:
        raise ValueError(f"mixed timestamp units in {key}")
    unit = str(units.iloc[0])
    frame["timestamp"] = pd.to_datetime(open_values, unit=unit, utc=True)
    for col in ["open", "high", "low", "close", "volume", "quote_volume", "taker_buy_base", "taker_buy_quote"]:
        frame[col] = pd.to_numeric(frame[col], errors="raise")
    frame["trade_count"] = pd.to_numeric(frame["trade_count"], errors="raise").astype("int64")
    out = frame[["timestamp", "open", "high", "low", "close", "volume", "quote_volume", "trade_count"]].copy()
    out = out.sort_values("timestamp")
    if out["timestamp"].duplicated().any():
        raise ValueError(f"duplicate timestamps inside archive: {key}")
    return out, digest


def _episode_market_id(symbol: str, episode_id: int) -> str:
    return f"{symbol}__E{episode_id:02d}"


def build_dataset(
    evidence_dir: str | Path,
    output_dir: str | Path,
    *,
    workers: int = 24,
    timeout: int = 60,
) -> dict:
    evidence = Path(evidence_dir)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    readiness = json.loads((evidence / "evidence-readiness.json").read_text(encoding="utf-8"))
    if readiness.get("decision") != "HISTORICAL_DOWNLOAD_READY" or not readiness.get("verified_lifecycle_ready"):
        raise ValueError(f"NO_GO: lifecycle evidence is not download-ready: {readiness.get('reasons')}")
    lifecycle_csv = evidence / "verified-lifecycle.csv"
    lifecycle_sha = file_sha256(lifecycle_csv)
    if lifecycle_sha != readiness.get("verified_lifecycle_sha256"):
        raise ValueError("NO_GO: verified lifecycle SHA does not match readiness certificate")
    unresolved = [x for x in readiness.get("symbols_without_monthly_1d", []) if not x.get("resolved")]
    if unresolved:
        raise ValueError(f"NO_GO: unresolved historical symbols: {[x['symbol'] for x in unresolved]}")

    observations = json.loads((evidence / "archive-observations.json").read_text(encoding="utf-8"))
    lifecycle = pd.read_csv(lifecycle_csv)
    by_symbol_month: dict[tuple[str, str], dict] = {
        (str(x["symbol"]), str(x["month"])): x for x in observations
    }

    episode_plans: list[dict] = []
    archive_keys: set[str] = set()
    for row in lifecycle.to_dict(orient="records"):
        symbol = str(row["symbol"])
        episode_id = int(row.get("episode_id", 1))
        first_month = str(row["first_archive_month"])
        last_month = str(row["last_archive_month"])
        first_ord = int(first_month[:4]) * 12 + int(first_month[5:7])
        last_ord = int(last_month[:4]) * 12 + int(last_month[5:7])
        selected = []
        for (obs_symbol, month), obs in by_symbol_month.items():
            if obs_symbol != symbol:
                continue
            ordinal = int(month[:4]) * 12 + int(month[5:7])
            if first_ord <= ordinal <= last_ord:
                selected.append(obs["key"])
        selected = sorted(set(selected))
        if not selected:
            raise ValueError(f"NO_GO: no archive plan for {symbol} episode {episode_id}")
        expected_months = int(row["archive_month_count"])
        if len(selected) != expected_months:
            raise ValueError(
                f"NO_GO: archive plan mismatch for {symbol} episode {episode_id}: {len(selected)} != {expected_months}"
            )
        archive_keys.update(selected)
        episode_plans.append({
            "market_id": _episode_market_id(symbol, episode_id),
            "symbol": symbol,
            "episode_id": episode_id,
            "listed_at": str(row["listed_at"]),
            "delisted_at": None if pd.isna(row.get("delisted_at")) else str(row["delisted_at"]),
            "keys": selected,
        })

    def fetch(key: str) -> tuple[str, pd.DataFrame, str]:
        frame, digest = parse_monthly_archive(key, timeout=timeout)
        return key, frame, digest

    fetched: dict[str, tuple[pd.DataFrame, str]] = {}
    failures: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(fetch, key): key for key in sorted(archive_keys)}
        for future in as_completed(futures):
            key = futures[future]
            try:
                _, frame, digest = future.result()
                fetched[key] = (frame, digest)
            except Exception as exc:
                failures.append({"key": key, "error": f"{type(exc).__name__}:{exc}"})
    if failures:
        (out / "archive-failures.json").write_text(json.dumps(failures, indent=2, sort_keys=True), encoding="utf-8")
        raise RuntimeError(f"NO_GO: {len(failures)} archive downloads/checksums failed")

    market_manifest: list[dict] = []
    archive_manifest: list[dict] = []
    for key in sorted(fetched):
        frame, digest = fetched[key]
        parts = key.split("/")
        symbol = parts[-3]
        month = parts[-1].replace(f"{symbol}-1d-", "").replace(".zip", "")
        archive_manifest.append(asdict(ArchiveFetch(
            symbol=symbol,
            month=month,
            key=key,
            sha256=digest,
            rows=len(frame),
            first_timestamp=frame["timestamp"].iloc[0].isoformat(),
            last_timestamp=frame["timestamp"].iloc[-1].isoformat(),
        )))

    market_dir = out / "market"
    market_dir.mkdir(parents=True, exist_ok=True)
    for plan in sorted(episode_plans, key=lambda x: x["market_id"]):
        chunks = [fetched[key][0] for key in plan["keys"]]
        frame = pd.concat(chunks, ignore_index=True).sort_values("timestamp")
        frame = frame.drop_duplicates(subset=["timestamp"], keep="first")
        listed = pd.Timestamp(plan["listed_at"])
        listed = listed.tz_localize("UTC") if listed.tzinfo is None else listed.tz_convert("UTC")
        frame = frame[frame["timestamp"] >= listed]
        if plan["delisted_at"]:
            delisted = pd.Timestamp(plan["delisted_at"])
            delisted = delisted.tz_localize("UTC") if delisted.tzinfo is None else delisted.tz_convert("UTC")
            frame = frame[frame["timestamp"] <= delisted]
        if frame.empty:
            raise ValueError(f"NO_GO: empty verified episode after boundary filter: {plan['market_id']}")
        if frame["timestamp"].duplicated().any() or not frame["timestamp"].is_monotonic_increasing:
            raise ValueError(f"NO_GO: invalid ordering for {plan['market_id']}")
        frame.insert(1, "symbol", plan["symbol"])
        frame.insert(2, "episode_id", plan["episode_id"])
        csv_path = market_dir / f"{plan['market_id']}.csv"
        frame.to_csv(csv_path, index=False, lineterminator="\n")
        gaps = frame["timestamp"].diff().dt.days.dropna()
        market_manifest.append({
            "market_id": plan["market_id"],
            "symbol": plan["symbol"],
            "episode_id": plan["episode_id"],
            "rows": len(frame),
            "first_timestamp": frame["timestamp"].iloc[0].isoformat(),
            "last_timestamp": frame["timestamp"].iloc[-1].isoformat(),
            "max_calendar_gap_days": int(gaps.max()) if not gaps.empty else 0,
            "csv_sha256": file_sha256(csv_path),
            "source_archive_count": len(plan["keys"]),
        })

    aggregate_lines = "".join(
        f"{x['market_id']} {x['csv_sha256']}\n" for x in sorted(market_manifest, key=lambda x: x["market_id"])
    ).encode("utf-8")
    dataset_sha = hashlib.sha256(aggregate_lines).hexdigest()
    manifest = {
        "schema_version": "1.0.0",
        "dataset_id": "ar-tf-binance-spot-usdt-1d-v1d2",
        "source": VISION_BASE,
        "point_in_time": True,
        "survivorship_bias_control": "verified lifecycle episodes including inactive/delisted historical markets",
        "verified_lifecycle_sha256": lifecycle_sha,
        "archive_observations_sha256": readiness["provenance"]["observations_sha256"],
        "archive_count": len(archive_manifest),
        "market_episode_count": len(market_manifest),
        "historical_symbol_count": len({x["symbol"] for x in market_manifest}),
        "excluded_no_1d_symbols": readiness.get("symbols_without_monthly_1d", []),
        "dataset_sha256": dataset_sha,
        "market_manifest_sha256": canonical_sha256(market_manifest),
        "archive_manifest_sha256": canonical_sha256(archive_manifest),
        "markets": market_manifest,
        "archives": archive_manifest,
        "holdout_evaluated": False,
        "paper_authorized": False,
    }
    (out / "dataset-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    (out / "dataset.sha256").write_text(dataset_sha + "  AR_TF_V1D2_DATASET\n", encoding="utf-8")
    return manifest


def main() -> None:
    p = argparse.ArgumentParser(description="Build full AR-TF v1-D2 Binance Spot 1d dataset")
    p.add_argument("--evidence-dir", required=True)
    p.add_argument("--output-dir", default="artifacts/ar_tf_v1d2_dataset")
    p.add_argument("--workers", type=int, default=24)
    p.add_argument("--timeout", type=int, default=60)
    args = p.parse_args()
    manifest = build_dataset(args.evidence_dir, args.output_dir, workers=args.workers, timeout=args.timeout)
    print(json.dumps({
        "dataset_id": manifest["dataset_id"],
        "dataset_sha256": manifest["dataset_sha256"],
        "archive_count": manifest["archive_count"],
        "market_episode_count": manifest["market_episode_count"],
        "historical_symbol_count": manifest["historical_symbol_count"],
        "holdout_evaluated": manifest["holdout_evaluated"],
        "paper_authorized": manifest["paper_authorized"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
