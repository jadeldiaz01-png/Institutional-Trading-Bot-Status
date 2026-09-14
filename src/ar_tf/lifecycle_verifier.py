from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, asdict
from pathlib import Path

import pandas as pd

from .evidence_acquisition import LifecycleCandidate, VISION_BASE

MARKET_DATA_EXCHANGE_INFO_URL = "https://data-api.binance.vision/api/v3/exchangeInfo"
PRIMARY_EXCHANGE_INFO_URL = "https://api.binance.com/api/v3/exchangeInfo"


@dataclass(frozen=True)
class VerifiedLifecycle:
    symbol: str
    listed_at: str
    delisted_at: str | None
    listing_evidence_url: str
    delisting_evidence_url: str
    listing_status: str
    delisting_status: str
    active_currently: bool
    first_archive_month: str
    last_archive_month: str
    archive_month_count: int
    archive_months_contiguous: bool
    first_boundary_zip_sha256: str
    last_boundary_zip_sha256: str
    episode_id: int = 1
    episode_count: int = 1
    evidence_method: str = "BINANCE_VISION_CHECKSUM_VERIFIED_TRADABLE_BOUNDARIES"


def _read_url(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "AR-TF-lifecycle/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def _zip_url(symbol: str, month: str) -> str:
    return f"{VISION_BASE}/data/spot/monthly/klines/{symbol}/1d/{symbol}-1d-{month}.zip"


def _checksum_url(symbol: str, month: str) -> str:
    return _zip_url(symbol, month) + ".CHECKSUM"


def _verify_checksum(payload: bytes, checksum_payload: bytes, expected_filename: str) -> str:
    text = checksum_payload.decode("utf-8").strip()
    match = re.search(r"([a-fA-F0-9]{64})\s+\*?(.+)$", text)
    if not match:
        raise ValueError(f"invalid checksum format for {expected_filename}")
    expected, filename = match.group(1).lower(), match.group(2).strip()
    if filename != expected_filename:
        raise ValueError(f"checksum filename mismatch: {filename} != {expected_filename}")
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise ValueError(f"checksum mismatch for {expected_filename}")
    return actual


def _timestamp_unit(value: int) -> str:
    # Binance Spot archive timestamps switched to microseconds from 2025 onward.
    return "us" if abs(value) >= 10**15 else "ms"


def _boundary_times(symbol: str, month: str, timeout: int = 60) -> tuple[pd.Timestamp, pd.Timestamp, str]:
    url = _zip_url(symbol, month)
    payload = _read_url(url, timeout)
    checksum = _read_url(_checksum_url(symbol, month), timeout)
    filename = f"{symbol}-1d-{month}.zip"
    digest = _verify_checksum(payload, checksum, filename)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        if len(names) != 1:
            raise ValueError(f"unexpected archive contents for {symbol} {month}: {names}")
        raw = archive.read(names[0]).decode("utf-8").strip().splitlines()
    if not raw:
        raise ValueError(f"empty boundary archive for {symbol} {month}")
    first = next(csv.reader([raw[0]]))
    last = next(csv.reader([raw[-1]]))
    first_open = int(first[0])
    last_close = int(last[6])
    start = pd.to_datetime(first_open, unit=_timestamp_unit(first_open), utc=True)
    end = pd.to_datetime(last_close, unit=_timestamp_unit(last_close), utc=True)
    return start, end, digest


def _month_ordinal(month: str) -> int:
    year, mon = map(int, month.split("-"))
    return year * 12 + mon


def months_contiguous(months: list[str]) -> bool:
    values = sorted({_month_ordinal(x) for x in months})
    return all(b - a == 1 for a, b in zip(values, values[1:]))


def current_spot_statuses(timeout: int = 60) -> dict[str, str]:
    """Return current public Spot symbol status without defining history from it."""
    errors: list[str] = []
    for url in (MARKET_DATA_EXCHANGE_INFO_URL, PRIMARY_EXCHANGE_INFO_URL):
        try:
            payload = json.loads(_read_url(url, timeout).decode("utf-8"))
            return {str(x["symbol"]): str(x.get("status", "UNKNOWN")) for x in payload.get("symbols", [])}
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            errors.append(f"{url}:{type(exc).__name__}:{exc}")
    raise RuntimeError("CURRENT_SPOT_STATUS_UNRESOLVED:" + " | ".join(errors))


def current_spot_symbols(timeout: int = 60) -> set[str]:
    """Compatibility helper: symbols that are currently TRADING only."""
    return {symbol for symbol, status in current_spot_statuses(timeout).items() if status == "TRADING"}


def verify_candidates(
    candidates: list[LifecycleCandidate],
    months_by_symbol: dict[str, list[str]],
    *,
    timeout: int = 60,
) -> tuple[list[VerifiedLifecycle], list[dict]]:
    """Legacy single-episode verifier retained for compatibility tests."""
    trading = current_spot_symbols(timeout)
    verified: list[VerifiedLifecycle] = []
    rejected: list[dict] = []
    for candidate in candidates:
        months = sorted(set(months_by_symbol.get(candidate.symbol, [])))
        contiguous = bool(months) and months_contiguous(months)
        if not contiguous:
            rejected.append({"symbol": candidate.symbol, "reason": "ARCHIVE_MONTH_GAP", "months": months})
            continue
        try:
            first_open, _, first_digest = _boundary_times(candidate.symbol, months[0], timeout)
            _, last_close, last_digest = _boundary_times(candidate.symbol, months[-1], timeout)
        except Exception as exc:
            rejected.append({"symbol": candidate.symbol, "reason": "BOUNDARY_VERIFICATION_FAILED", "detail": str(exc)})
            continue
        is_active = candidate.symbol in trading
        verified.append(
            VerifiedLifecycle(
                symbol=candidate.symbol,
                listed_at=first_open.isoformat(),
                delisted_at=None if is_active else last_close.isoformat(),
                listing_evidence_url=_zip_url(candidate.symbol, months[0]),
                delisting_evidence_url="" if is_active else _zip_url(candidate.symbol, months[-1]),
                listing_status="VERIFIED",
                delisting_status="NOT_APPLICABLE" if is_active else "VERIFIED",
                active_currently=is_active,
                first_archive_month=months[0],
                last_archive_month=months[-1],
                archive_month_count=len(months),
                archive_months_contiguous=True,
                first_boundary_zip_sha256=first_digest,
                last_boundary_zip_sha256=last_digest,
            )
        )
    return verified, rejected


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_verified_lifecycle(rows: list[VerifiedLifecycle], rejected: list[dict], output_dir: str | Path) -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    columns = list(VerifiedLifecycle.__dataclass_fields__)
    if rows:
        df = pd.DataFrame([asdict(x) for x in rows], columns=columns).sort_values(["symbol", "episode_id"])
    else:
        df = pd.DataFrame(columns=columns)
    csv_path = out / "verified-lifecycle.csv"
    df.to_csv(csv_path, index=False, lineterminator="\n")
    digest = file_sha256(csv_path)
    (out / "verified-lifecycle.sha256").write_text(digest + "  verified-lifecycle.csv\n", encoding="utf-8")
    (out / "lifecycle-rejected.json").write_text(json.dumps(rejected, indent=2, sort_keys=True), encoding="utf-8")
    summary = {
        "verified_rows": len(rows),
        "verified_symbols": len({x.symbol for x in rows}),
        "multi_episode_symbols": len({x.symbol for x in rows if x.episode_count > 1}),
        "rejected_rows": len(rejected),
        "verified_lifecycle_sha256": digest,
        "certification_complete": len(rejected) == 0 and len(rows) > 0,
        "definition": "checksum-verified observed Binance Spot tradability episodes",
    }
    (out / "lifecycle-verification-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary
