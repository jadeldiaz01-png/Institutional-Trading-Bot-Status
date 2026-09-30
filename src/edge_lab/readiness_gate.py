"""Automatic, research-only M0→M7 readiness gate.

This module may run an ablation only after the point-in-time dataset is ready.
It never grants EDGE_VERIFIED or execution authority.
"""

from __future__ import annotations

import csv
import hashlib
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


def load_panel_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [{k: _coerce(v) for k, v in row.items()} for row in csv.DictReader(handle)]
    if not rows:
        raise ValueError("point-in-time panel is empty")
    return rows


def _assert_research_only_authority(readiness: dict[str, Any]) -> None:
    assert readiness["EDGE_VERIFIED"] is False
    assert readiness["holdout_accessed"] is False
    assert readiness["paper_authorized"] is False
    assert readiness["testnet_authorized"] is False
    assert readiness["live_authorized"] is False


def evaluate_readiness_gate(
    *,
    readiness: dict[str, Any],
    rows: list[dict[str, Any]],
    protocol: dict[str, Any],
    metadata: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    _assert_research_only_authority(readiness)
    metadata = metadata or {}

    base = {
        "schema_version": "1.0.0",
        "mode": "RESEARCH_ONLY",
        "run_id": metadata.get("run_id"),
        "run_attempt": metadata.get("run_attempt"),
        "workflow_source_sha": metadata.get("workflow_source_sha"),
        "EDGE_VERIFIED": False,
        "holdout_accessed": False,
        "paper_authorized": False,
        "testnet_authorized": False,
        "live_authorized": False,
    }

    if not readiness["history_ready_for_first_fold"]:
        state = {
            **base,
            "status": "WAITING_FOR_PROSPECTIVE_DATA",
            "decision_timestamps": int(readiness["decision_timestamps"]),
            "minimum_timestamps_for_first_fold": int(readiness["minimum_timestamps_for_first_fold"]),
            "eligible_models": [],
            "blocked_models": [],
            "next_gate": "CONTINUE_AUTOMATIC_ACCUMULATION",
        }
        return state, None

    report = evaluate_models(rows, protocol)
    assert report["EDGE_VERIFIED"] is False
    assert report["holdout_accessed"] is False
    assert report["paper_authorized"] is False
    assert report["testnet_authorized"] is False
    assert report["live_authorized"] is False

    serialized = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode("utf-8")
    state = {
        **base,
        "status": "RESEARCH_ABLATION_COMPLETE",
        "decision_timestamps": int(readiness["decision_timestamps"]),
        "minimum_timestamps_for_first_fold": int(readiness["minimum_timestamps_for_first_fold"]),
        "eligible_models": list(report["eligible_models"]),
        "blocked_models": list(report["blocked_models"]),
        "ablation_report_sha256": hashlib.sha256(serialized).hexdigest(),
        "next_gate": "HUMAN_REVIEW_OF_RESEARCH_RESULTS",
    }
    return state, report


def write_gate_outputs(
    *,
    readiness_path: Path,
    panel_path: Path,
    protocol_path: Path,
    output_dir: Path,
    metadata: dict[str, str] | None = None,
) -> dict[str, Any]:
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    rows = load_panel_csv(panel_path)
    state, report = evaluate_readiness_gate(
        readiness=readiness,
        rows=rows,
        protocol=protocol,
        metadata=metadata,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = output_dir / "ablation-state.json"
    if report is not None:
        report_path = output_dir / "ablation-report.json"
        report_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        actual = hashlib.sha256(report_path.read_bytes()).hexdigest()
        if actual != state["ablation_report_sha256"]:
            raise RuntimeError("ablation report digest mismatch")

    state_path.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return state
