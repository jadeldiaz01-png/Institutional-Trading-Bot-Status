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
from .gap_evidence import classify_gap_report, load_registry
from .lifecycle_verifier import _timestamp_unit, file_sha256

_LOCK = threading.Lock()
_ANOMALIES: list[dict] = []
DEFAULT_EVENT_REGISTRY = "config/ar_tf_market_event_registry_2026.json"
_MARKET_NUMERIC_COLUMNS = ["open", "high", "low", "close", "volume", "quote_volume", "trade_count"]


def _row_sha256(row: list[str]) -> str:
    payload = json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _record(entry: dict) -> None:
    with _LOCK:
        _ANOMALIES.append(entry)


def _parse_reconciled_zip(payload: bytes, key: str, source_sha256: str) -> pd.DataFrame:
    """Parse a Binance Vision kline ZIP with deterministic duplicate reconciliation."""
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


def _market_row_invariant_reasons(row: pd.Series) -> list[str]:
    """Return deterministic physical-market invariant violations for one 1d kline row."""
    numeric = pd.to_numeric(row[_MARKET_NUMERIC_COLUMNS], errors="coerce")
    if bool(numeric.isna().any()):
        return ["NON_NUMERIC_OHLCV"]
    reasons: list[str] = []
    if bool((numeric[["open", "high", "low", "close"]] <= 0).any()):
        reasons.append("NON_POSITIVE_PRICE")
    if bool((numeric[["volume", "quote_volume", "trade_count"]] < 0).any()):
        reasons.append("NEGATIVE_ACTIVITY")
    if float(numeric["high"]) < max(float(numeric["open"]), float(numeric["close"]), float(numeric["low"])):
        reasons.append("HIGH_INVARIANT")
    if float(numeric["low"]) > min(float(numeric["open"]), float(numeric["close"]), float(numeric["high"])):
        reasons.append("LOW_INVARIANT")
    return reasons


def _market_row_payload(row: pd.Series) -> dict:
    return {
        "timestamp": pd.Timestamp(row["timestamp"]).isoformat(),
        **{column: str(row[column]) for column in _MARKET_NUMERIC_COLUMNS},
    }


def _recompute_manifest_market_identity(output_dir: Path, manifest: dict) -> dict:
    """Rebind every market CSV and dataset SHA after any checksum-verified row replacement."""
    markets = manifest["markets"]
    for market in markets:
        market["csv_sha256"] = file_sha256(output_dir / "market" / f"{market['market_id']}.csv")
    aggregate_lines = "".join(
        f"{x['market_id']} {x['csv_sha256']}\n" for x in sorted(markets, key=lambda x: x["market_id"])
    ).encode("utf-8")
    manifest["dataset_sha256"] = hashlib.sha256(aggregate_lines).hexdigest()
    manifest["market_manifest_sha256"] = canonical_sha256(markets)
    (output_dir / "dataset-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    (output_dir / "dataset.sha256").write_text(
        manifest["dataset_sha256"] + "  AR_TF_V1D2_DATASET\n", encoding="utf-8"
    )
    return manifest


def _reconcile_market_invariants_from_daily(
    output_dir: Path,
    manifest: dict,
    *,
    timeout: int = 60,
) -> dict:
    """Adjudicate invalid monthly-derived rows only with same-day official daily archives.

    No interpolation, clipping, price adjustment, future observation or statistical
    imputation is allowed. A row is replaced only when the exact Binance Vision
    daily 1d ZIP exists, its CHECKSUM verifies, contains exactly one matching UTC
    day, and the replacement independently satisfies every physical kline invariant.
    Otherwise the anomaly remains unresolved and dataset certification fails closed.
    """
    reconciliations: list[dict] = []
    any_replacement = False
    market_by_id = {x["market_id"]: x for x in manifest["markets"]}

    for market_id in sorted(market_by_id):
        market = market_by_id[market_id]
        path = output_dir / "market" / f"{market_id}.csv"
        frame = pd.read_csv(path)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
        if frame["timestamp"].isna().any():
            continue
        changed = False
        for idx, row in frame.iterrows():
            reasons = _market_row_invariant_reasons(row)
            if not reasons:
                continue
            timestamp = pd.Timestamp(row["timestamp"])
            symbol = str(row["symbol"])
            day_text = timestamp.strftime("%Y-%m-%d")
            daily_key = f"data/spot/daily/klines/{symbol}/1d/{symbol}-1d-{day_text}.zip"
            original_payload = _market_row_payload(row)
            original_sha = canonical_sha256(original_payload)
            base = {
                "schema_version": "1.0.0",
                "anomaly_type": "+".join(sorted(reasons)),
                "market_id": market_id,
                "symbol": symbol,
                "timestamp": timestamp.isoformat(),
                "source_key": daily_key,
                "open_time_raw": str(int(timestamp.timestamp() * 1000)),
                "original_row_sha256": original_sha,
                "original_reasons": sorted(reasons),
            }
            try:
                daily, digest = _download_reconciled_zip(daily_key, timeout=timeout)
                if len(daily) != 1:
                    raise ValueError(f"daily 1d archive must contain exactly one row: {daily_key}: {len(daily)}")
                candidate = daily.iloc[0].copy()
                candidate_ts = pd.Timestamp(candidate["timestamp"])
                candidate_ts = candidate_ts.tz_localize("UTC") if candidate_ts.tzinfo is None else candidate_ts.tz_convert("UTC")
                if candidate_ts != timestamp:
                    raise ValueError(
                        f"daily archive timestamp mismatch: {daily_key}: {candidate_ts.isoformat()} != {timestamp.isoformat()}"
                    )
                candidate_reasons = _market_row_invariant_reasons(candidate)
                replacement_payload = _market_row_payload(candidate)
                replacement_sha = canonical_sha256(replacement_payload)
                if candidate_reasons:
                    entry = {
                        **base,
                        "source_sha256": digest,
                        "state": "UNRESOLVED",
                        "resolution": "DAILY_ARCHIVE_INVARIANT_FAILED_FAIL_CLOSED",
                        "replacement_row_sha256": replacement_sha,
                        "replacement_reasons": sorted(candidate_reasons),
                    }
                    entry["resolution_sha256"] = canonical_sha256({
                        "market_id": market_id,
                        "timestamp": timestamp.isoformat(),
                        "source_sha256": digest,
                        "original_row_sha256": original_sha,
                        "replacement_row_sha256": replacement_sha,
                        "method": entry["resolution"],
                    })
                    _record(entry)
                    reconciliations.append(entry)
                    continue

                for column in ["open", "high", "low", "close", "volume", "quote_volume", "trade_count"]:
                    frame.at[idx, column] = candidate[column]
                entry = {
                    **base,
                    "source_sha256": digest,
                    "state": "RESOLVED",
                    "resolution": "CHECKSUM_VERIFIED_SAME_DAY_DAILY_ROW_REPLACEMENT",
                    "replacement_row_sha256": replacement_sha,
                    "replacement_reasons": [],
                }
                entry["resolution_sha256"] = canonical_sha256({
                    "market_id": market_id,
                    "timestamp": timestamp.isoformat(),
                    "source_sha256": digest,
                    "original_row_sha256": original_sha,
                    "replacement_row_sha256": replacement_sha,
                    "method": entry["resolution"],
                })
                _record(entry)
                reconciliations.append(entry)
                changed = True
                any_replacement = True
            except Exception as exc:
                entry = {
                    **base,
                    "source_sha256": None,
                    "state": "UNRESOLVED",
                    "resolution": "DAILY_ARCHIVE_RECONCILIATION_FAILED_FAIL_CLOSED",
                    "error": f"{type(exc).__name__}:{exc}",
                }
                entry["resolution_sha256"] = canonical_sha256({
                    "market_id": market_id,
                    "timestamp": timestamp.isoformat(),
                    "original_row_sha256": original_sha,
                    "error": entry["error"],
                    "method": entry["resolution"],
                })
                _record(entry)
                reconciliations.append(entry)

        if changed:
            frame.to_csv(path, index=False, lineterminator="\n")

    manifest["row_reconciliations"] = reconciliations
    manifest["row_reconciliation_attempt_count"] = len(reconciliations)
    manifest["row_reconciliation_resolved_count"] = sum(x["state"] == "RESOLVED" for x in reconciliations)
    manifest["row_reconciliation_manifest_sha256"] = canonical_sha256(reconciliations)
    if any_replacement:
        manifest = _recompute_manifest_market_identity(output_dir, manifest)
    else:
        (output_dir / "dataset-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
    return manifest


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
    internal_gap_daily_verified = 0
    row_reconciliation_daily_verified = 0

    for archive in manifest["archives"]:
        digest = str(archive.get("sha256", ""))
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
            invalid.append({"key": archive.get("key"), "reason": "invalid_archive_digest"})
        source_mode = archive.get("source_mode")
        if source_mode in {
            "MONTHLY_CHECKSUM_VERIFIED",
            "MONTHLY_CHECKSUM_VERIFIED_WITH_DAILY_GAP_RECOVERY",
        }:
            monthly_verified += 1
        elif source_mode == "DAILY_CHECKSUM_RECONSTRUCTED":
            reconstructed_months += 1

    for reconstruction in manifest.get("reconstructions", []):
        for source in reconstruction.get("daily_sources", []):
            daily_verified += 1
            digest = str(source.get("sha256", ""))
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
                invalid.append({"key": source.get("key"), "reason": "invalid_daily_digest"})

    for repair in manifest.get("internal_gap_repairs", []):
        if repair.get("state") != "RESOLVED":
            continue
        for source in repair.get("sources", []):
            internal_gap_daily_verified += 1
            digest = str(source.get("sha256", ""))
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
                invalid.append({"key": source.get("key"), "reason": "invalid_internal_gap_daily_digest"})

    for repair in manifest.get("row_reconciliations", []):
        if repair.get("state") != "RESOLVED":
            continue
        row_reconciliation_daily_verified += 1
        digest = str(repair.get("source_sha256", ""))
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
            invalid.append({"key": repair.get("source_key"), "reason": "invalid_row_reconciliation_daily_digest"})

    return {
        "schema_version": "1.2.0",
        "archive_plan_count": manifest["archive_count"],
        "monthly_checksum_verified_count": monthly_verified,
        "daily_reconstructed_month_count": reconstructed_months,
        "daily_checksum_verified_source_count": daily_verified,
        "internal_gap_daily_checksum_verified_source_count": internal_gap_daily_verified,
        "row_reconciliation_daily_checksum_verified_source_count": row_reconciliation_daily_verified,
        "invalid_checksum_evidence_count": len(invalid),
        "invalid": invalid,
        "all_source_checksums_verified": len(invalid) == 0,
    }


def _source_plan_hashes(path: Path) -> tuple[str, str]:
    """Return semantic and byte-level identities for archive-observations.json."""
    value = json.loads(path.read_text(encoding="utf-8"))
    return canonical_sha256(value), file_sha256(path)


def certify_dataset(
    evidence_dir: str | Path,
    output_dir: str | Path,
    *,
    workers: int = 16,
    timeout: int = 60,
    market_event_registry: str | Path = DEFAULT_EVENT_REGISTRY,
) -> dict:
    global _ANOMALIES
    _ANOMALIES = []
    evidence = Path(evidence_dir)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    original_download = hd._download_verified_zip
    try:
        hd._download_verified_zip = _download_reconciled_zip
        manifest = hd.build_dataset(evidence, out, workers=workers, timeout=timeout)
    finally:
        hd._download_verified_zip = original_download

    manifest = _reconcile_market_invariants_from_daily(out, manifest, timeout=timeout)

    anomalies = sorted(
        _ANOMALIES,
        key=lambda x: (x["source_key"], x["open_time_raw"], x["state"], x["resolution_sha256"]),
    )
    unresolved_anomalies = [x for x in anomalies if x["state"] != "RESOLVED"]
    anomaly_ledger = {
        "schema_version": "1.1.0",
        "policy": (
            "exact-identical duplicates may collapse; conflicting rows fail closed; "
            "physical OHLCV invariant violations may be replaced only by the exact same-day "
            "Binance Vision daily row after independent CHECKSUM and invariant verification"
        ),
        "resolved_count": len(anomalies) - len(unresolved_anomalies),
        "unresolved_count": len(unresolved_anomalies),
        "entries": anomalies,
    }
    anomaly_path = out / "reconciliation-ledger.json"
    anomaly_path.write_text(json.dumps(anomaly_ledger, indent=2, sort_keys=True), encoding="utf-8")

    raw_gaps = _gap_report(out, manifest)
    registry = load_registry(market_event_registry)
    gaps = classify_gap_report(raw_gaps, registry)
    gaps["market_episode_count"] = raw_gaps["market_episode_count"]
    gaps["checked_rows"] = raw_gaps["checked_rows"]
    gaps["raw_observed_gap_count"] = len(raw_gaps["events"])
    gap_path = out / "gap-report.json"
    gap_path.write_text(json.dumps(gaps, indent=2, sort_keys=True), encoding="utf-8")

    checksums = _checksum_report(manifest)
    checksum_path = out / "checksum-report.json"
    checksum_path.write_text(json.dumps(checksums, indent=2, sort_keys=True), encoding="utf-8")

    lifecycle_sha = file_sha256(evidence / "verified-lifecycle.csv")
    manifest_path = out / "dataset-manifest.json"
    manifest_sha = file_sha256(manifest_path)
    source_plan_sha, source_plan_file_sha = _source_plan_hashes(evidence / "archive-observations.json")
    unresolved_count = (
        anomaly_ledger["unresolved_count"]
        + gaps["unresolved_gap_count"]
        + checksums["invalid_checksum_evidence_count"]
    )
    lifecycle_binding_ok = lifecycle_sha == manifest["verified_lifecycle_sha256"]
    source_plan_binding_ok = source_plan_sha == manifest["archive_observations_sha256"]
    if not lifecycle_binding_ok:
        unresolved_count += 1
    if not source_plan_binding_ok:
        unresolved_count += 1

    certificate = {
        "schema_version": "1.3.0",
        "decision": "FROZEN_DATASET" if unresolved_count == 0 else "NO_GO",
        "dataset_id": manifest["dataset_id"],
        "dataset_sha256": manifest["dataset_sha256"],
        "dataset_manifest_sha256": manifest_sha,
        "verified_lifecycle_sha256": lifecycle_sha,
        "lifecycle_binding_verified": lifecycle_binding_ok,
        "source_plan_sha256": source_plan_sha,
        "source_plan_file_sha256": source_plan_file_sha,
        "source_plan_binding_verified": source_plan_binding_ok,
        "market_event_registry_sha256": canonical_sha256(registry),
        "internal_gap_repair_manifest_sha256": manifest.get("internal_gap_repair_manifest_sha256"),
        "internal_gap_repair_attempt_count": manifest.get("internal_gap_repair_attempt_count", 0),
        "internal_gap_repair_resolved_count": manifest.get("internal_gap_repair_resolved_count", 0),
        "row_reconciliation_manifest_sha256": manifest.get("row_reconciliation_manifest_sha256"),
        "row_reconciliation_attempt_count": manifest.get("row_reconciliation_attempt_count", 0),
        "row_reconciliation_resolved_count": manifest.get("row_reconciliation_resolved_count", 0),
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
        "observed_gap_count": gaps["observed_gap_count"],
        "resolved_gap_count": gaps["resolved_gap_count"],
        "unresolved_gap_count": gaps["unresolved_gap_count"],
        "invalid_checksum_evidence_count": checksums["invalid_checksum_evidence_count"],
        "unresolved_count": unresolved_count,
        "code_sha": os.environ.get("AR_TF_CODE_SHA") or os.environ.get("GITHUB_SHA") or "UNKNOWN",
        "frozen": unresolved_count == 0,
        "holdout_evaluated": False,
        "paper_authorized": False,
        "testnet_authorized": False,
        "shadow_authorized": False,
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
    parser.add_argument("--market-event-registry", default=DEFAULT_EVENT_REGISTRY)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    certificate = certify_dataset(
        args.evidence_dir,
        args.output_dir,
        workers=args.workers,
        timeout=args.timeout,
        market_event_registry=args.market_event_registry,
    )
    print(json.dumps(certificate, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
