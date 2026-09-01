from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .evidence_acquisition import (
    acquire_usdt_daily_keys,
    extract_usdt_daily_observations,
    lifecycle_candidates,
    validate_verified_lifecycle,
    verified_lifecycle_sha256,
    write_discovery_bundle,
)
from .lifecycle_verifier import verify_candidates, write_verified_lifecycle


def main() -> None:
    p = argparse.ArgumentParser(description="AR-TF v1-D2 historical evidence acquisition")
    p.add_argument("--output-dir", default="artifacts/ar_tf_v1d2")
    p.add_argument("--verified-lifecycle", default=None)
    p.add_argument("--timeout", type=int, default=60)
    p.add_argument("--skip-boundary-verification", action="store_true")
    args = p.parse_args()

    symbols, keys = acquire_usdt_daily_keys(timeout=args.timeout)
    provenance = write_discovery_bundle(args.output_dir, keys, discovered_symbols=symbols)

    result = {
        "stage": "RESEARCH",
        "decision": "NO_GO",
        "paper_authorized": False,
        "provenance": provenance,
        "verified_lifecycle_ready": False,
        "verified_lifecycle_sha256": None,
        "reasons": ["VERIFIED_LIFECYCLE_NOT_AVAILABLE"],
    }

    lifecycle_path: str | None = args.verified_lifecycle
    if not lifecycle_path and not args.skip_boundary_verification:
        observations = extract_usdt_daily_observations(keys)
        candidates = lifecycle_candidates(observations)
        months_by_symbol: dict[str, list[str]] = {}
        for obs in observations:
            months_by_symbol.setdefault(obs.symbol, []).append(obs.month)
        verified, rejected = verify_candidates(candidates, months_by_symbol, timeout=args.timeout)
        summary = write_verified_lifecycle(verified, rejected, args.output_dir)
        result["boundary_verification"] = summary
        lifecycle_path = str(Path(args.output_dir) / "verified-lifecycle.csv")
        if rejected:
            result["reasons"] = ["HISTORICAL_LIFECYCLE_HAS_REJECTED_SYMBOLS"]

    if lifecycle_path:
        rows = pd.read_csv(lifecycle_path)
        reasons = validate_verified_lifecycle(rows)
        if not reasons and result.get("boundary_verification", {}).get("rejected_rows", 0) == 0:
            result["reasons"] = []
            result["verified_lifecycle_ready"] = True
            result["verified_lifecycle_sha256"] = verified_lifecycle_sha256(rows)
            result["decision"] = "HISTORICAL_DOWNLOAD_READY"
        else:
            result["reasons"] = sorted(set(result.get("reasons", []) + reasons))

    output = Path(args.output_dir) / "evidence-readiness.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
