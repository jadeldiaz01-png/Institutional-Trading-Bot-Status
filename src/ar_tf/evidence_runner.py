from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .evidence_acquisition import (
    list_binance_vision_keys,
    validate_verified_lifecycle,
    write_discovery_bundle,
)


def main() -> None:
    p = argparse.ArgumentParser(description="AR-TF v1-D2 historical evidence acquisition")
    p.add_argument("--output-dir", default="artifacts/ar_tf_v1d2")
    p.add_argument("--prefix", default="data/spot/monthly/klines/")
    p.add_argument("--max-pages", type=int, default=None)
    p.add_argument("--verified-lifecycle", default=None)
    args = p.parse_args()

    keys = list_binance_vision_keys(args.prefix, max_pages=args.max_pages)
    provenance = write_discovery_bundle(args.output_dir, keys)

    result = {
        "stage": "RESEARCH",
        "decision": "NO_GO",
        "paper_authorized": False,
        "provenance": provenance,
        "verified_lifecycle_ready": False,
        "reasons": ["VERIFIED_LIFECYCLE_NOT_SUPPLIED"],
    }

    if args.verified_lifecycle:
        rows = pd.read_csv(args.verified_lifecycle)
        reasons = validate_verified_lifecycle(rows)
        result["reasons"] = reasons
        result["verified_lifecycle_ready"] = not reasons
        result["decision"] = "HISTORICAL_DOWNLOAD_READY" if not reasons else "NO_GO"

    output = Path(args.output_dir) / "evidence-readiness.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
