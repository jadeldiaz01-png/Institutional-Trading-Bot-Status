from __future__ import annotations

import argparse
import json
from pathlib import Path

from .evidence_acquisition import canonical_sha256
from .lifecycle_verifier import file_sha256


FINAL_STATES = {"VERIFIED_STRUCTURAL_GAP", "VERIFIED_LIFECYCLE_SPLIT", "VERIFIED_DAILY_RECONSTRUCTION"}


def _load(path: str | Path) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def semantic_json_sha256(path: str | Path) -> str:
    """Hash JSON by the same canonical semantics used by evidence acquisition.

    This intentionally differs from file_sha256(): pretty-printing, whitespace and
    key order must not change the semantic provenance hash.
    """
    return canonical_sha256(_load(path))


def audit_p0_data_001(
    evidence_dir: str | Path,
    dataset_dir: str | Path,
    resolution_file: str | Path,
) -> dict:
    evidence = Path(evidence_dir)
    dataset = Path(dataset_dir)
    manifest = _load(dataset / "dataset-manifest.json")
    gaps = _load(dataset / "gap-report.json")
    resolutions_doc = _load(resolution_file)

    expected_source_plan_sha = str(manifest["archive_observations_sha256"])
    semantic_source_plan_sha = semantic_json_sha256(evidence / "archive-observations.json")
    byte_source_plan_sha = file_sha256(evidence / "archive-observations.json")
    semantic_hash_match = semantic_source_plan_sha == expected_source_plan_sha

    raw_events = {
        (str(x["market_id"]), str(x["previous"]), str(x["current"])): x
        for x in gaps.get("events", [])
    }
    resolutions = {
        (str(x["market_id"]), str(x["previous"]), str(x["current"])): x
        for x in resolutions_doc.get("resolutions", [])
    }

    missing_resolution_records = sorted(
        {"market_id": key[0], "previous": key[1], "current": key[2]}
        for key in raw_events.keys() - resolutions.keys()
    , key=lambda x: (x["market_id"], x["previous"], x["current"]))
    stale_resolution_records = sorted(
        {"market_id": key[0], "previous": key[1], "current": key[2]}
        for key in resolutions.keys() - raw_events.keys()
    , key=lambda x: (x["market_id"], x["previous"], x["current"]))

    verified = []
    pending = []
    for key in sorted(raw_events.keys() & resolutions.keys()):
        record = resolutions[key]
        entry = {
            "market_id": key[0],
            "previous": key[1],
            "current": key[2],
            "classification": record.get("classification"),
            "state": record.get("state"),
            "evidence": record.get("evidence", []),
        }
        if record.get("state") in FINAL_STATES:
            verified.append(entry)
        else:
            pending.append(entry)

    blockers: list[str] = []
    if not semantic_hash_match:
        blockers.append("SOURCE_PLAN_SEMANTIC_HASH_MISMATCH")
    if missing_resolution_records:
        blockers.append("GAP_WITHOUT_RESOLUTION_RECORD")
    if stale_resolution_records:
        blockers.append("STALE_RESOLUTION_RECORD")
    if pending:
        blockers.append("GAP_RESOLUTION_NOT_VERIFIED")

    # The old byte-wise comparison is diagnostic only. It is expected to differ
    # from the canonical provenance hash and MUST NOT increment unresolved_count.
    result = {
        "schema_version": "1.0.0",
        "decision": "P0_DATA_001_CLOSED" if not blockers else "NO_GO",
        "semantic_source_plan_sha256": semantic_source_plan_sha,
        "expected_source_plan_sha256": expected_source_plan_sha,
        "byte_source_plan_sha256_diagnostic_only": byte_source_plan_sha,
        "semantic_hash_match": semantic_hash_match,
        "raw_gap_count": len(raw_events),
        "verified_gap_resolution_count": len(verified),
        "pending_gap_resolution_count": len(pending),
        "missing_resolution_records": missing_resolution_records,
        "stale_resolution_records": stale_resolution_records,
        "verified": verified,
        "pending": pending,
        "blockers": blockers,
        "frozen_dataset_authorized": not blockers,
        "holdout_evaluated": False,
        "paper_authorized": False,
        "testnet_authorized": False,
        "live_authorized": False,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit P0-DATA-001 dataset reconciliation closure")
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--dataset-dir", required=True)
    parser.add_argument("--resolutions", default="config/ar_tf_gap_resolutions_v1.json")
    parser.add_argument("--output", default="artifacts/p0-data-001-status.json")
    args = parser.parse_args()

    result = audit_p0_data_001(args.evidence_dir, args.dataset_dir, args.resolutions)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["decision"] != "P0_DATA_001_CLOSED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
