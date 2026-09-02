from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from pathlib import Path

import pandas as pd

from .evidence_acquisition import VISION_BASE, canonical_sha256, list_binance_vision_keys
from .lifecycle_verifier import _timestamp_unit, file_sha256

KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trade_count", "taker_buy_base", "taker_buy_quote", "ignore",
]
DAILY_KEY_RE = re.compile(
    r"^data/spot/daily/klines/(?P<symbol>[A-Z0-9]+)/1d/(?P=symbol)-1d-(?P<date>\d{4}-\d{2}-\d{2})\.zip$"
)


@dataclass(frozen=True)
class ArchiveFetch:
    symbol: str
    month: str
    key: str
    sha256: str
    rows: int
    first_timestamp: str
    last_timestamp: str
    source_mode: str
    monthly_failure: str | None = None
    daily_source_count: int = 0
    daily_sources_sha256: str | None = None


def _read_with_retry(url: str, *, timeout: int = 60, attempts: int = 4) -> bytes:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AR-TF-dataset/1.1"})
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


def _parse_zip_payload(payload: bytes, key: str) -> pd.DataFrame:
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
    return out


def _download_verified_zip(key: str, *, timeout: int = 60) -> tuple[pd.DataFrame, str]:
    url = f"{VISION_BASE}/{key}"
    payload = _read_with_retry(url, timeout=timeout)
    checksum_payload = _read_with_retry(url + ".CHECKSUM", timeout=timeout)
    filename = key.rsplit("/", 1)[-1]
    digest = _verify_checksum(payload, checksum_payload, filename)
    return _parse_zip_payload(payload, key), digest


def parse_monthly_archive(key: str, *, timeout: int = 60) -> tuple[pd.DataFrame, str]:
    return _download_verified_zip(key, timeout=timeout)


def _utc_day(value: str | pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return ts.normalize()


def _month_bounds(month: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(f"{month}-01", tz="UTC")
    return start, start + pd.offsets.MonthEnd(1)


def _expected_daily_bounds(month: str, listed_at: str, delisted_at: str | None) -> tuple[pd.Timestamp, pd.Timestamp]:
    month_start, month_end = _month_bounds(month)
    start = max(month_start, _utc_day(listed_at))
    end = month_end if not delisted_at else min(month_end, _utc_day(delisted_at))
    if end < start:
        raise ValueError(f"invalid expected daily bounds for {month}: {start} > {end}")
    return start, end


def reconstruct_month_from_daily(
    symbol: str,
    month: str,
    *,
    expected_start: pd.Timestamp,
    expected_end: pd.Timestamp,
    timeout: int = 60,
) -> tuple[pd.DataFrame, str, list[dict]]:
    """Reconstruct one malformed monthly 1d archive from checksum-verified daily archives.

    The fallback uses only official Binance Vision daily 1d ZIPs. Every daily ZIP
    must pass its own CHECKSUM and the reconstructed dates must exactly cover the
    lifecycle-constrained expected calendar days for the month. Missing or extra
    days fail closed rather than being imputed.
    """
    prefix = f"data/spot/daily/klines/{symbol}/1d/{symbol}-1d-{month}-"
    keys = sorted(k for k in list_binance_vision_keys(prefix, timeout=timeout) if DAILY_KEY_RE.match(k))
    if not keys:
        raise ValueError(f"no daily fallback archives for {symbol} {month}")

    frames: list[pd.DataFrame] = []
    sources: list[dict] = []
    for key in keys:
        match = DAILY_KEY_RE.match(key)
        assert match is not None
        day = pd.Timestamp(match.group("date"), tz="UTC")
        if day < expected_start or day > expected_end:
            continue
        frame, digest = _download_verified_zip(key, timeout=timeout)
        if len(frame) != 1:
            raise ValueError(f"daily 1d archive must contain exactly one row: {key}: {len(frame)}")
        if frame["timestamp"].iloc[0].normalize() != day:
            raise ValueError(f"daily archive date mismatch: {key}: {frame['timestamp'].iloc[0]}")
        frames.append(frame)
        sources.append({"key": key, "sha256": digest})

    if not frames:
        raise ValueError(f"no daily rows within expected lifecycle bounds for {symbol} {month}")
    out = pd.concat(frames, ignore_index=True).sort_values("timestamp")
    if out["timestamp"].duplicated().any():
        raise ValueError(f"duplicate timestamps after daily reconstruction: {symbol} {month}")

    expected_days = pd.date_range(expected_start, expected_end, freq="D", tz="UTC")
    actual_days = pd.DatetimeIndex(out["timestamp"].dt.normalize())
    if not actual_days.equals(expected_days):
        missing = expected_days.difference(actual_days)
        extra = actual_days.difference(expected_days)
        raise ValueError(
            f"daily fallback coverage mismatch {symbol} {month}: "
            f"missing={[x.date().isoformat() for x in missing]} extra={[x.date().isoformat() for x in extra]}"
        )
    source_digest = canonical_sha256(sources)
    return out, source_digest, sources


def _episode_market_id(symbol: str, episode_id: int) -> str:
    return f"{symbol}__E{episode_id:02d}"


def _key_symbol_month(key: str) -> tuple[str, str]:
    parts = key.split("/")
    symbol = parts[-3]
    month = parts[-1].replace(f"{symbol}-1d-", "").replace(".zip", "")
    return symbol, month


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
    key_bounds: dict[str, tuple[pd.Timestamp, pd.Timestamp]] = {}
    for row in lifecycle.to_dict(orient="records"):
        symbol = str(row["symbol"])
        episode_id = int(row.get("episode_id", 1))
        first_month = str(row["first_archive_month"])
        last_month = str(row["last_archive_month"])
        first_ord = int(first_month[:4]) * 12 + int(first_month[5:7])
        last_ord = int(last_month[:4]) * 12 + int(last_month[5:7])
        listed_at = str(row["listed_at"])
        delisted_at = None if pd.isna(row.get("delisted_at")) else str(row["delisted_at"])
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
        for key in selected:
            _, month = _key_symbol_month(key)
            bounds = _expected_daily_bounds(month, listed_at, delisted_at)
            if key in key_bounds and key_bounds[key] != bounds:
                raise ValueError(f"NO_GO: archive key maps to conflicting lifecycle bounds: {key}")
            key_bounds[key] = bounds
        archive_keys.update(selected)
        episode_plans.append({
            "market_id": _episode_market_id(symbol, episode_id),
            "symbol": symbol,
            "episode_id": episode_id,
            "listed_at": listed_at,
            "delisted_at": delisted_at,
            "keys": selected,
        })

    def fetch(key: str) -> tuple[str, pd.DataFrame, str, dict]:
        symbol, month = _key_symbol_month(key)
        try:
            frame, digest = parse_monthly_archive(key, timeout=timeout)
            return key, frame, digest, {
                "source_mode": "MONTHLY_CHECKSUM_VERIFIED",
                "monthly_failure": None,
                "daily_source_count": 0,
                "daily_sources_sha256": None,
                "daily_sources": [],
            }
        except Exception as monthly_exc:
            start, end = key_bounds[key]
            frame, digest, sources = reconstruct_month_from_daily(
                symbol, month, expected_start=start, expected_end=end, timeout=timeout
            )
            return key, frame, digest, {
                "source_mode": "DAILY_CHECKSUM_RECONSTRUCTED",
                "monthly_failure": f"{type(monthly_exc).__name__}:{monthly_exc}",
                "daily_source_count": len(sources),
                "daily_sources_sha256": digest,
                "daily_sources": sources,
            }

    fetched: dict[str, tuple[pd.DataFrame, str, dict]] = {}
    failures: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(fetch, key): key for key in sorted(archive_keys)}
        for future in as_completed(futures):
            key = futures[future]
            try:
                _, frame, digest, metadata = future.result()
                fetched[key] = (frame, digest, metadata)
            except Exception as exc:
                failures.append({"key": key, "error": f"{type(exc).__name__}:{exc}"})
    if failures:
        (out / "archive-failures.json").write_text(json.dumps(failures, indent=2, sort_keys=True), encoding="utf-8")
        raise RuntimeError(f"NO_GO: {len(failures)} archive downloads/checksums failed after daily fallback")

    market_manifest: list[dict] = []
    archive_manifest: list[dict] = []
    reconstruction_manifest: list[dict] = []
    for key in sorted(fetched):
        frame, digest, metadata = fetched[key]
        symbol, month = _key_symbol_month(key)
        archive_manifest.append(asdict(ArchiveFetch(
            symbol=symbol,
            month=month,
            key=key,
            sha256=digest,
            rows=len(frame),
            first_timestamp=frame["timestamp"].iloc[0].isoformat(),
            last_timestamp=frame["timestamp"].iloc[-1].isoformat(),
            source_mode=metadata["source_mode"],
            monthly_failure=metadata["monthly_failure"],
            daily_source_count=metadata["daily_source_count"],
            daily_sources_sha256=metadata["daily_sources_sha256"],
        )))
        if metadata["source_mode"] == "DAILY_CHECKSUM_RECONSTRUCTED":
            reconstruction_manifest.append({
                "symbol": symbol,
                "month": month,
                "monthly_key": key,
                "monthly_failure": metadata["monthly_failure"],
                "daily_source_count": metadata["daily_source_count"],
                "daily_sources_sha256": metadata["daily_sources_sha256"],
                "daily_sources": metadata["daily_sources"],
            })

    market_dir = out / "market"
    market_dir.mkdir(parents=True, exist_ok=True)
    for plan in sorted(episode_plans, key=lambda x: x["market_id"]):
        chunks = [fetched[key][0] for key in plan["keys"]]
        frame = pd.concat(chunks, ignore_index=True).sort_values("timestamp")
        if frame["timestamp"].duplicated().any():
            raise ValueError(f"NO_GO: duplicate timestamps across verified archives: {plan['market_id']}")
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
        "schema_version": "1.1.0",
        "dataset_id": "ar-tf-binance-spot-usdt-1d-v1d2",
        "source": VISION_BASE,
        "point_in_time": True,
        "survivorship_bias_control": "verified lifecycle episodes including inactive/delisted historical markets",
        "verified_lifecycle_sha256": lifecycle_sha,
        "archive_observations_sha256": readiness["provenance"]["observations_sha256"],
        "archive_count": len(archive_manifest),
        "reconstructed_archive_count": len(reconstruction_manifest),
        "reconstruction_manifest_sha256": canonical_sha256(reconstruction_manifest),
        "market_episode_count": len(market_manifest),
        "historical_symbol_count": len({x["symbol"] for x in market_manifest}),
        "excluded_no_1d_symbols": readiness.get("symbols_without_monthly_1d", []),
        "dataset_sha256": dataset_sha,
        "market_manifest_sha256": canonical_sha256(market_manifest),
        "archive_manifest_sha256": canonical_sha256(archive_manifest),
        "markets": market_manifest,
        "archives": archive_manifest,
        "reconstructions": reconstruction_manifest,
        "holdout_evaluated": False,
        "paper_authorized": False,
    }
    (out / "dataset-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    (out / "dataset.sha256").write_text(dataset_sha + "  AR_TF_V1D2_DATASET\n", encoding="utf-8")
    (out / "daily-reconstructions.json").write_text(
        json.dumps(reconstruction_manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
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
        "reconstructed_archive_count": manifest["reconstructed_archive_count"],
        "market_episode_count": manifest["market_episode_count"],
        "historical_symbol_count": manifest["historical_symbol_count"],
        "holdout_evaluated": manifest["holdout_evaluated"],
        "paper_authorized": manifest["paper_authorized"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
