#!/usr/bin/env python3
"""Run the automatic research-only readiness gate."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from edge_lab.readiness_gate import write_gate_outputs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readiness", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--protocol", default="experiments/m0_m7_edge_search/protocol.json")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    state = write_gate_outputs(
        readiness_path=Path(args.readiness),
        panel_path=Path(args.input),
        protocol_path=Path(args.protocol),
        output_dir=Path(args.output_dir),
        metadata={
            "run_id": os.environ.get("GITHUB_RUN_ID", ""),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
            "workflow_source_sha": os.environ.get("GITHUB_SHA", ""),
        },
    )

    print("ABLATION_GATE=" + state["status"])
    print(
        "READINESS="
        + str(state["decision_timestamps"])
        + "/"
        + str(state["minimum_timestamps_for_first_fold"])
    )
    print("ELIGIBLE_MODELS=" + ",".join(state["eligible_models"]))
    print("BLOCKED_MODELS=" + ",".join(state["blocked_models"]))
    print("NEXT_GATE=" + state["next_gate"])
    print("EDGE_VERIFIED=false")
    print("LIVE_AUTHORIZED=false")


if __name__ == "__main__":
    main()
