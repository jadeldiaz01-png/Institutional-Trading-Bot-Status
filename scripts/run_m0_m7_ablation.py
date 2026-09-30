#!/usr/bin/env python3
"""Run the research-only M0→M7 ablation on a point-in-time CSV panel."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from edge_lab.ablation import evaluate_models


def _coerce(value: str) -> Any:
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return value


def load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [{k: _coerce(v) for k, v in row.items()} for row in csv.DictReader(handle)]
    if not rows:
        raise ValueError("input CSV is empty")

    keys: list[tuple[str, str]] = []
    timestamps: list[str] = []
    for row in rows:
        timestamp = str(row.get("timestamp", ""))
        if not timestamp:
            raise ValueError("every row requires timestamp")
        asset = str(row.get("asset") or "__portfolio__")
        keys.append((timestamp, asset))
        timestamps.append(timestamp)

    if timestamps != sorted(timestamps):
        raise ValueError("rows must be sorted by timestamp ascending")
    if len(set(keys)) != len(keys):
        raise ValueError("timestamp/asset pairs must be unique")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--protocol", default="experiments/m0_m7_edge_search/protocol.json")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    protocol = json.loads(Path(args.protocol).read_text(encoding="utf-8"))
    rows = load_rows(Path(args.input))
    report = evaluate_models(rows, protocol)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"M0_M7_REPORT={output}")
    print(f"ASSET_COUNT={report['panel']['asset_count']}")
    print(f"DECISION_TIMESTAMPS={report['panel']['decision_timestamps']}")
    print("EDGE_VERIFIED=false")
    print("LIVE_AUTHORIZED=false")


if __name__ == "__main__":
    main()
