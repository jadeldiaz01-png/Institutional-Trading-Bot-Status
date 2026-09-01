from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .evidence_acquisition import (
    acquire_usdt_daily_keys,
    validate_verified_lifecycle,
    verified_lifecycle_sha256,
    write_discovery_bundle,
)


def main() -> None:
    p = argparse.ArgumentParser(description="AR-TF v1-D2 historical evidence acquisition")
    p.add_argument("--output-dir", default="artifacts/ar_tf_v1d2")
    p.add_argument("--verified-lifecycle", default=None)
    p.add_argument("--timeout", type=int, default=60)
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
        "reasons": ["VERIFIED_LIFECYCLE_NOT_SUPPLIED"],
    }

    if args.verified_lifecycle:
        rows = pd.read_csv(args.verified_lifecycle)
        reasons = validate_verified_lifecycle(rows)
        result["reasons"] = reasons
        result["verified_lifecycle_ready"] = not reasons
        result["verified_lifecycle_sha256"] = verified_lifecycle_sha256(rows) if not reasons else None
        result["decision"] = "HISTORICAL_DOWNLOAD_READY" if not reasons else "NO_GO"

    output = Path(args.output_dir) / "evidence-readiness.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
