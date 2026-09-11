from __future__ import annotations

import json

from ar_tf.evidence_acquisition import canonical_sha256
from ar_tf.p0_data_001 import audit_p0_data_001, semantic_json_sha256


def test_semantic_json_hash_ignores_pretty_printing(tmp_path):
    payload = [{"b": 2, "a": 1}]
    path = tmp_path / "observations.json"
    path.write_text(json.dumps(payload, indent=4, sort_keys=False), encoding="utf-8")
    assert semantic_json_sha256(path) == canonical_sha256(payload)


def test_p0_data_001_remains_no_go_until_gap_states_verified(tmp_path):
    evidence = tmp_path / "evidence"
    dataset = tmp_path / "dataset"
    evidence.mkdir()
    dataset.mkdir()

    observations = [{"symbol": "XUSDT", "month": "2024-01", "key": "k", "source_url": "https://example.test/k"}]
    (evidence / "archive-observations.json").write_text(json.dumps(observations, indent=2), encoding="utf-8")
    expected = canonical_sha256(observations)

    (dataset / "dataset-manifest.json").write_text(json.dumps({"archive_observations_sha256": expected}), encoding="utf-8")
    event = {"market_id": "XUSDT__E01", "previous": "2024-01-01T00:00:00+00:00", "current": "2024-01-03T00:00:00+00:00", "type": "INTERNAL_CALENDAR_GAP"}
    (dataset / "gap-report.json").write_text(json.dumps({"events": [event]}), encoding="utf-8")

    resolutions = tmp_path / "resolutions.json"
    resolutions.write_text(json.dumps({"resolutions": [{
        "market_id": event["market_id"],
        "previous": event["previous"],
        "current": event["current"],
        "classification": "TRADING_HALT",
        "state": "EVIDENCE_IDENTIFIED",
        "evidence": ["https://example.test/announcement"],
    }]}), encoding="utf-8")

    result = audit_p0_data_001(evidence, dataset, resolutions)
    assert result["semantic_hash_match"] is True
    assert result["decision"] == "NO_GO"
    assert result["pending_gap_resolution_count"] == 1
    assert result["frozen_dataset_authorized"] is False


def test_p0_data_001_closes_only_with_final_state(tmp_path):
    evidence = tmp_path / "evidence"
    dataset = tmp_path / "dataset"
    evidence.mkdir()
    dataset.mkdir()

    observations = [{"symbol": "XUSDT", "month": "2024-01", "key": "k", "source_url": "https://example.test/k"}]
    (evidence / "archive-observations.json").write_text(json.dumps(observations), encoding="utf-8")
    (dataset / "dataset-manifest.json").write_text(json.dumps({"archive_observations_sha256": canonical_sha256(observations)}), encoding="utf-8")
    event = {"market_id": "XUSDT__E01", "previous": "2024-01-01T00:00:00+00:00", "current": "2024-01-03T00:00:00+00:00", "type": "INTERNAL_CALENDAR_GAP"}
    (dataset / "gap-report.json").write_text(json.dumps({"events": [event]}), encoding="utf-8")

    resolutions = tmp_path / "resolutions.json"
    resolutions.write_text(json.dumps({"resolutions": [{
        "market_id": event["market_id"],
        "previous": event["previous"],
        "current": event["current"],
        "classification": "TRADING_HALT",
        "state": "VERIFIED_STRUCTURAL_GAP",
        "evidence": ["https://example.test/announcement"],
    }]}), encoding="utf-8")

    result = audit_p0_data_001(evidence, dataset, resolutions)
    assert result["decision"] == "P0_DATA_001_CLOSED"
    assert result["verified_gap_resolution_count"] == 1
    assert result["frozen_dataset_authorized"] is True
