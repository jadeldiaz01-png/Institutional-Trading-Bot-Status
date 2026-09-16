from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .evidence_acquisition import (
    extract_usdt_daily_observations,
    lifecycle_candidates,
    list_binance_vision_keys,
    validate_verified_lifecycle,
    write_discovery_bundle,
)
from .evidence_parallel import acquire_usdt_daily_keys_parallel, verify_candidates_parallel
from .lifecycle_verifier import current_spot_statuses, file_sha256, write_verified_lifecycle

DAILY_KLINE_PREFIX = "data/spot/daily/klines/"


def resolve_symbols_without_monthly_1d(
    discovered_symbols: list[str],
    observations,
    *,
    timeout: int,
) -> list[dict]:
    """Resolve every discovered symbol omitted from monthly 1d evidence.

    A symbol with no monthly 1d archive is never silently discarded. We query
    the daily 1d archive separately. If daily files exist, the lifecycle remains
    unresolved until those files are ingested. If neither monthly nor daily 1d
    archives exist, it is explicitly excluded from the 1d research universe as
    NO_1D_ARCHIVE_EVIDENCE, while remaining in provenance.
    """
    observed = {x.symbol for x in observations}
    missing = sorted(set(discovered_symbols) - observed)
    statuses = current_spot_statuses(timeout) if missing else {}
    rows: list[dict] = []
    for symbol in missing:
        daily_prefix = f"{DAILY_KLINE_PREFIX}{symbol}/1d/"
        daily_keys = sorted(
            k for k in list_binance_vision_keys(daily_prefix, timeout=timeout)
            if k.endswith(".zip") and not k.endswith(".CHECKSUM.zip")
        )
        if daily_keys:
            resolution = "DAILY_ONLY_1D_EVIDENCE_REQUIRES_INGESTION"
            resolved = False
            included = False
        else:
            resolution = "NO_1D_ARCHIVE_EVIDENCE"
            resolved = True
            included = False
        rows.append({
            "symbol": symbol,
            "current_status": statuses.get(symbol, "ABSENT"),
            "monthly_1d_archive_count": 0,
            "daily_1d_archive_count": len(daily_keys),
            "first_daily_1d_key": daily_keys[0] if daily_keys else None,
            "last_daily_1d_key": daily_keys[-1] if daily_keys else None,
            "resolution": resolution,
            "resolved": resolved,
            "research_universe_included": included,
        })
    return rows


def main() -> None:
    p = argparse.ArgumentParser(description="AR-TF v1-D2 historical evidence acquisition")
    p.add_argument("--output-dir", default="artifacts/ar_tf_v1d2")
    p.add_argument("--verified-lifecycle", default=None)
    p.add_argument("--timeout", type=int, default=60)
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--skip-boundary-verification", action="store_true")
    args = p.parse_args()

    symbols, keys = acquire_usdt_daily_keys_parallel(timeout=args.timeout, workers=args.workers)
    provenance = write_discovery_bundle(args.output_dir, keys, discovered_symbols=symbols)
    observations = extract_usdt_daily_observations(keys)
    no_monthly = resolve_symbols_without_monthly_1d(symbols, observations, timeout=args.timeout)
    unresolved_no_monthly = [x for x in no_monthly if not x["resolved"]]
    Path(args.output_dir, "symbols-without-monthly-1d.json").write_text(
        json.dumps(no_monthly, indent=2, sort_keys=True), encoding="utf-8"
    )

    result = {
        "stage": "RESEARCH",
        "decision": "NO_GO",
        "paper_authorized": False,
        "provenance": provenance,
        "verified_lifecycle_ready": False,
        "verified_lifecycle_sha256": None,
        "symbols_without_monthly_1d": no_monthly,
        "all_discovered_symbols_resolved": not unresolved_no_monthly,
        "reasons": ["VERIFIED_LIFECYCLE_NOT_AVAILABLE"],
    }
    if unresolved_no_monthly:
        result["reasons"].append("DAILY_ONLY_1D_SYMBOLS_REQUIRE_INGESTION")

    lifecycle_path: str | None = args.verified_lifecycle
    if not lifecycle_path and not args.skip_boundary_verification:
        candidates = lifecycle_candidates(observations)
        months_by_symbol: dict[str, list[str]] = {}
        for obs in observations:
            months_by_symbol.setdefault(obs.symbol, []).append(obs.month)
        verified, rejected = verify_candidates_parallel(
            candidates, months_by_symbol, timeout=args.timeout, workers=args.workers
        )
        summary = write_verified_lifecycle(verified, rejected, args.output_dir)
        result["boundary_verification"] = summary
        lifecycle_path = str(Path(args.output_dir) / "verified-lifecycle.csv")
        if rejected:
            result["reasons"] = ["HISTORICAL_LIFECYCLE_HAS_REJECTED_EPISODES"] + (
                ["DAILY_ONLY_1D_SYMBOLS_REQUIRE_INGESTION"] if unresolved_no_monthly else []
            )

    if lifecycle_path:
        rows = pd.read_csv(lifecycle_path)
        reasons = validate_verified_lifecycle(rows)
        digest = file_sha256(lifecycle_path)
        expected_digest = result.get("boundary_verification", {}).get("verified_lifecycle_sha256")
        if expected_digest and digest != expected_digest:
            reasons.append("VERIFIED_LIFECYCLE_SHA256_MISMATCH")
        if unresolved_no_monthly:
            reasons.append("DAILY_ONLY_1D_SYMBOLS_REQUIRE_INGESTION")
        if not reasons and result.get("boundary_verification", {}).get("rejected_rows", 0) == 0:
            result["reasons"] = []
            result["verified_lifecycle_ready"] = True
            result["verified_lifecycle_sha256"] = digest
            result["decision"] = "HISTORICAL_DOWNLOAD_READY"
        else:
            result["reasons"] = sorted(set(result.get("reasons", []) + reasons))

    output = Path(args.output_dir) / "evidence-readiness.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
