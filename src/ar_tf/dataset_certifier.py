from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import threading
import zipfile
from pathlib import Path

import pandas as pd

from . import historical_dataset as hd
from .evidence_acquisition import canonical_sha256
from .lifecycle_verifier import _timestamp_unit, file_sha256

_LOCK = threading.Lock()
_ANOMALIES: list[dict] = []


def _row_sha256(row: list[str]) -> str:
    payload = json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _record(entry: dict) -> None:
    with _LOCK:
        _ANOMALIES.append(entry)


def _parse_reconciled_zip(payload: bytes, key: str, source_sha256: str) -> pd.DataFrame:
    """Parse a Binance Vision kline ZIP with deterministic duplicate reconciliation.

    Duplicate timestamps are accepted only when every original CSV field is exactly
    identical. Conflicting duplicates remain fail-closed. The decision is recorded
    in a deterministic anomaly ledger bound to the source ZIP checksum.
    """
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        if len(names) != 1:
            raise ValueError(f"unexpected archive contents: {key}: {names}")
        rows = list(csv.reader(io.TextIOWrapper(archive.open(names[0]), encoding="utf-8")))
    if not rows:
        raise ValueError(f"empty archive: {key}")
    if any(len(row) != len(hd.KLINE_COLUMNS) for row in rows):
        raise ValueError(f"unexpected kline column count: {key}")

    by_open_time: dict[str, list[list[str]]] = {}
    for row in rows:
        by_open_time.setdefault(row[0], []).append(row)

    reconciled: list[list[str]] = []
    for open_time in sorted(by_open_time, key=lambda x: int(x)):
        group = by_open_time[open_time]
        if len(group) == 1:
            reconciled.append(group[0])
            continue

        row_hashes = sorted(_row_sha256(row) for row in group)
        unique_rows = {tuple(row) for row in group}
        timestamp_unit = _timestamp_unit(int(open_time))
        timestamp = pd.to_datetime(int(open_time), unit=timestamp_unit, utc=True).isoformat()
        base = {
            "schema_version": "1.0.0",
            "anomaly_type": "DUPLICATE_TIMESTAMP",
            "source_key": key,
            "source_sha256": source_sha256,
            "open_time_raw": open_time,
            "timestamp": timestamp,
            "copy_count": len(group),
            "row_hashes": row_hashes,
            "unique_row_count": len(unique_rows),
        }
        if len(unique_rows) == 1:
            survivor = group[0]
            survivor_sha = _row_sha256(survivor)
            _record({
                **base,
                "state": "RESOLVED",
                "resolution": "COLLAPSE_EXACT_IDENTICAL_ROWS",
                "survivor_row_sha256": survivor_sha,
                "resolution_sha256": canonical_sha256({
                    "source_sha256": source_sha256,
                    "open_time_raw": open_time,
                    "copy_count": len(group),
                    "survivor_row_sha256": survivor_sha,
                    "method": "COLLAPSE_EXACT_IDENTICAL_ROWS",
                }),
            })
            reconciled.append(survivor)
            continue

        _record({
            **base,
            "state": "UNRESOLVED",
            "resolution": "CONFLICTING_ROWS_FAIL_CLOSED",
            "resolution_sha256": canonical_sha256({
                "source_sha256": source_sha256,
                "open_time_raw": open_time,
                "row_hashes": row_hashes,
                "method": "CONFLICTING_ROWS_FAIL_CLOSED",
            }),
        })
        raise ValueError(f"conflicting duplicate timestamp inside archive: {key}: {timestamp}")

    frame = pd.DataFrame(reconciled, columns=hd.KLINE_COLUMNS)
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
    out = out.sort_values("timestamp").reset_index(drop=True)
    if out["timestamp"].duplicated().any():
        raise ValueError(f"duplicate timestamps remain after reconciliation: {key}")
    return out


def _download_reconciled_zip(key: str, *, timeout: int = 60) -> tuple[pd.DataFrame, str]:
    url = f"{hd.VISION_BASE}/{key}"
    payload = hd._read_with_retry(url, timeout=timeout)
    checksum_payload = hd._read_with_retry(url + ".CHECKSUM", timeout=timeout)
    filename = key.rsplit("/", 1)[-1]
    digest = hd._verify_checksum(payload, checksum_payload, filename)
    return _parse_reconciled_zip(payload, key, digest), digest


def _gap_report(dataset_dir: Path, manifest: dict) -> dict:
    events: list[dict] = []
    checked_rows = 0
    for market in sorted(manifest["markets"], key=lambda x: x["market_id"]):
        path = dataset_dir / "market" / f"{market['market_id']}.csv"
        frame = pd.read_csv(path, parse_dates=["timestamp"])
        if frame.empty:
            events.append({"market_id": market["market_id"], "type": "EMPTY_MARKET"})
            continue
        ts = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True)).sort_values()
        checked_rows += len(ts)
        if ts.duplicated().any():
            events.append({"market_id": market["market_id"], "type": "DUPLICATE_TIMESTAMP"})
        non_midnight = [x.isoformat() for x in ts if x != x.normalize()]
        if non_midnight:
            events.append({
                "market_id": market["market_id"],
                "type": "NON_DAILY_BOUNDARY_TIMESTAMP",
                "timestamps": non_midnight,
            })
        diffs = pd.Series(ts).diff().dropna()
        for idx, delta in diffs.items():
            if delta != pd.Timedelta(days=1):
                previous = ts[idx - 1]
                current = ts[idx]
                events.append({
                    "market_id": market["market_id"],
                    "type": "INTERNAL_CALENDAR_GAP",
                    "previous": previous.isoformat(),
                    "current": current.isoformat(),
                    "gap_days": int(delta / pd.Timedelta(days=1)),
                })
    return {
        "schema_version": "1.0.0",
        "market_episode_count": len(manifest["markets"]),
        "checked_rows": checked_rows,
        "unresolved_gap_count": len(events),
        "events": events,
    }


def _checksum_report(manifest: dict) -> dict:
    invalid: list[dict] = []
    monthly_verified = 0
    reconstructed_months = 0
    daily_verified = 0
    for archive in manifest["archives"]:
        digest = str(archive.get("sha256", ""))
        if len(digest) != 64:
            invalid.append({"key": archive.get("key"), "reason": "invalid_archive_digest"})
        if archive.get("source_mode") == "MONTHLY_CHECKSUM_VERIFIED":
            monthly_verified += 1
        elif archive.get("source_mode") == "DAILY_CHECKSUM_RECONSTRUCTED":
            reconstructed_months += 1

    for reconstruction in manifest.get("reconstructions", []):
        for source in reconstruction.get("daily_sources", []):
            daily_verified += 1
            if len(str(source.get("sha256", ""))) != 64:
                invalid.append({"key": source.get("key"), "reason": "invalid_daily_digest"})

    return {
        "schema_version": "1.0.0",
        "archive_plan_count": manifest["archive_count"],
        "monthly_checksum_verified_count": monthly_verified,
        "daily_reconstructed_month_count": reconstructed_months,
        "daily_checksum_verified_source_count": daily_verified,
        "invalid_checksum_evidence_count": len(invalid),
        "invalid": invalid,
        "all_source_checksums_verified": len(invalid) == 0,
    }


def certify_dataset(evidence_dir: str | Path, output_dir: str | Path, *, workers: int = 16, timeout: int = 60) -> dict:
    global _ANOMALIES
    _ANOMALIES = []
    evidence = Path(evidence_dir)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Patch only the verified ZIP parser/downloader. The historical planning,
    # lifecycle boundaries, source selection and dataset construction remain in
    # v1-D2 and therefore retain their existing provenance contract.
    original_download = hd._download_verified_zip
    try:
        hd._download_verified_zip = _download_reconciled_zip
        manifest = hd.build_dataset(evidence, out, workers=workers, timeout=timeout)
    finally:
        hd._download_verified_zip = original_download

    anomalies = sorted(
        _ANOMALIES,
        key=lambda x: (x["source_key"], x["open_time_raw"], x["state"], x["resolution_sha256"]),
    )
    unresolved_anomalies = [x for x in anomalies if x["state"] != "RESOLVED"]
    anomaly_ledger = {
        "schema_version": "1.0.0",
        "policy": "exact-identical duplicates may collapse; conflicting rows fail closed",
        "resolved_count": len(anomalies) - len(unresolved_anomalies),
        "unresolved_count": len(unresolved_anomalies),
        "entries": anomalies,
    }
    anomaly_path = out / "reconciliation-ledger.json"
    anomaly_path.write_text(json.dumps(anomaly_ledger, indent=2, sort_keys=True), encoding="utf-8")

    gaps = _gap_report(out, manifest)
    gap_path = out / "gap-report.json"
    gap_path.write_text(json.dumps(gaps, indent=2, sort_keys=True), encoding="utf-8")

    checksums = _checksum_report(manifest)
    checksum_path = out / "checksum-report.json"
    checksum_path.write_text(json.dumps(checksums, indent=2, sort_keys=True), encoding="utf-8")

    lifecycle_sha = file_sha256(evidence / "verified-lifecycle.csv")
    manifest_path = out / "dataset-manifest.json"
    manifest_sha = file_sha256(manifest_path)
    source_plan_sha = file_sha256(evidence / "archive-observations.json")
    unresolved_count = (
        anomaly_ledger["unresolved_count"]
        + gaps["unresolved_gap_count"]
        + checksums["invalid_checksum_evidence_count"]
    )
    if lifecycle_sha != manifest["verified_lifecycle_sha256"]:
        unresolved_count += 1
    if source_plan_sha != manifest["archive_observations_sha256"]:
        unresolved_count += 1

    certificate = {
        "schema_version": "1.0.0",
        "decision": "FROZEN_DATASET" if unresolved_count == 0 else "NO_GO",
        "dataset_id": manifest["dataset_id"],
        "dataset_sha256": manifest["dataset_sha256"],
        "dataset_manifest_sha256": manifest_sha,
        "verified_lifecycle_sha256": lifecycle_sha,
        "source_plan_sha256": source_plan_sha,
        "reconciliation_ledger_sha256": file_sha256(anomaly_path),
        "gap_report_sha256": file_sha256(gap_path),
        "checksum_report_sha256": file_sha256(checksum_path),
        "market_manifest_sha256": manifest["market_manifest_sha256"],
        "archive_manifest_sha256": manifest["archive_manifest_sha256"],
        "archive_count": manifest["archive_count"],
        "market_episode_count": manifest["market_episode_count"],
        "historical_symbol_count": manifest["historical_symbol_count"],
        "resolved_anomaly_count": anomaly_ledger["resolved_count"],
        "unresolved_anomaly_count": anomaly_ledger["unresolved_count"],
        "unresolved_gap_count": gaps["unresolved_gap_count"],
        "invalid_checksum_evidence_count": checksums["invalid_checksum_evidence_count"],
        "unresolved_count": unresolved_count,
        "code_sha": os.environ.get("AR_TF_CODE_SHA") or os.environ.get("GITHUB_SHA") or "UNKNOWN",
        "frozen": unresolved_count == 0,
        "holdout_evaluated": False,
        "paper_authorized": False,
        "testnet_authorized": False,
        "live_authorized": False,
    }
    cert_path = out / "dataset-freeze-certificate.json"
    cert_path.write_text(json.dumps(certificate, indent=2, sort_keys=True), encoding="utf-8")
    (out / "dataset-freeze-certificate.sha256").write_text(
        file_sha256(cert_path) + "  dataset-freeze-certificate.json\n", encoding="utf-8"
    )

    if unresolved_count != 0:
        raise RuntimeError(f"NO_GO: dataset certification has unresolved_count={unresolved_count}")
    return certificate


def main() -> None:
    parser = argparse.ArgumentParser(description="Certify and freeze AR-TF v1-D2 historical dataset")
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--output-dir", default="artifacts/ar_tf_v1d2_dataset")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    certificate = certify_dataset(
        args.evidence_dir,
        args.output_dir,
        workers=args.workers,
        timeout=args.timeout,
    )
    print(json.dumps(certificate, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
