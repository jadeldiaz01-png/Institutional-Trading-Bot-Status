#!/usr/bin/env python3
"""Build the leakage-controlled point-in-time M0→M7 research panel."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from edge_lab.feature_pipeline import (
    build_point_in_time_panel,
    load_derivative_bars,
    load_derivative_metrics,
    load_onchain,
    load_spot_bars,
    readiness_report,
    write_panel_csv,
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--protocol", default="experiments/m0_m7_edge_search/protocol.json")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    root = Path(args.input_dir)
    protocol = json.loads(Path(args.protocol).read_text(encoding="utf-8"))
    authority = protocol["authority"]
    assert authority["edge_verified"] is False
    assert authority["holdout_access"] == "FORBIDDEN"
    assert authority["paper_authorized"] is False
    assert authority["testnet_authorized"] is False
    assert authority["live_authorized"] is False

    panel = build_point_in_time_panel(
        load_spot_bars(root),
        benchmark_symbol="BTCUSDT",
        derivative_bars=load_derivative_bars(root),
        derivative_metrics=load_derivative_metrics(root),
        derivative_map={"BTCUSDT": "BTCUSD_PERP"},
        onchain=load_onchain(root),
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    panel_path = output_dir / "point_in_time_panel.csv"
    readiness_path = output_dir / "readiness.json"
    manifest_path = output_dir / "feature-manifest.json"

    write_panel_csv(panel, panel_path)
    readiness = readiness_report(panel, protocol)
    readiness_path.write_text(json.dumps(readiness, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "1.0.0",
        "mode": "RESEARCH_ONLY",
        "panel_path": str(panel_path),
        "panel_sha256": sha256_file(panel_path),
        "readiness_path": str(readiness_path),
        "readiness_sha256": sha256_file(readiness_path),
        "row_count": len(panel),
        "decision_timestamps": readiness["decision_timestamps"],
        "asset_count": readiness["asset_count"],
        "assets": readiness["assets"],
        "point_in_time_contract": {
            "decision_timestamp": "source bar close time",
            "feature_cutoff": "source_event_time <= decision_timestamp",
            "forward_return_role": "label_only_strictly_after_decision_timestamp",
            "onchain_availability": "daily metric usable no earlier than metric_day_plus_1d",
            "future_feature_access": False
        },
        "safety": {
            "holdout_accessed": False,
            "EDGE_VERIFIED": False,
            "paper_authorized": False,
            "testnet_authorized": False,
            "live_authorized": False
        },
        "decision": readiness["decision"]
    }
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    print(f"POINT_IN_TIME_PANEL={panel_path}")
    print(f"PANEL_SHA256={manifest['panel_sha256']}")
    print(f"DECISION_TIMESTAMPS={readiness['decision_timestamps']}")
    print(f"ASSET_COUNT={readiness['asset_count']}")
    print(f"DATASET_DECISION={readiness['decision']}")
    print("EDGE_VERIFIED=false")
    print("LIVE_AUTHORIZED=false")


if __name__ == "__main__":
    main()
