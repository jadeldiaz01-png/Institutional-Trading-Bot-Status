import csv
import hashlib
import io
import json
import zipfile

import pandas as pd
import pytest

import ar_tf.dataset_certifier as dc


def _raw_row(open_time: int, close: str = "1.0") -> list[str]:
    return [
        str(open_time), "1.0", "1.1", "0.9", close, "100.0", str(open_time + 86399999),
        "1000.0", "10", "50.0", "500.0", "0",
    ]


def _zip(rows: list[list[str]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        text = io.StringIO()
        writer = csv.writer(text, lineterminator="\n")
        writer.writerows(rows)
        zf.writestr("rows.csv", text.getvalue())
    return buffer.getvalue()


def test_identical_duplicate_is_collapsed_and_ledgered():
    dc._ANOMALIES = []
    t = 1770681600000
    row = _raw_row(t)
    payload = _zip([row, row])
    digest = hashlib.sha256(payload).hexdigest()
    frame = dc._parse_reconciled_zip(payload, "data/spot/daily/klines/AXSUSDT/1d/AXSUSDT-1d-2026-02-10.zip", digest)
    assert len(frame) == 1
    assert len(dc._ANOMALIES) == 1
    anomaly = dc._ANOMALIES[0]
    assert anomaly["state"] == "RESOLVED"
    assert anomaly["resolution"] == "COLLAPSE_EXACT_IDENTICAL_ROWS"
    assert anomaly["copy_count"] == 2
    assert anomaly["unique_row_count"] == 1
    assert anomaly["source_sha256"] == digest
    assert len(anomaly["resolution_sha256"]) == 64


def test_conflicting_duplicate_fails_closed_and_is_ledgered():
    dc._ANOMALIES = []
    t = 1784073600000
    payload = _zip([_raw_row(t, "1.0"), _raw_row(t, "1.2")])
    digest = hashlib.sha256(payload).hexdigest()
    with pytest.raises(ValueError, match="conflicting duplicate timestamp"):
        dc._parse_reconciled_zip(payload, "data/spot/daily/klines/UMAUSDT/1d/UMAUSDT-1d-2026-07-15.zip", digest)
    assert len(dc._ANOMALIES) == 1
    anomaly = dc._ANOMALIES[0]
    assert anomaly["state"] == "UNRESOLVED"
    assert anomaly["resolution"] == "CONFLICTING_ROWS_FAIL_CLOSED"
    assert anomaly["unique_row_count"] == 2


def test_duplicate_resolution_hash_is_deterministic():
    t = 1784246400000
    row = _raw_row(t)
    payload = _zip([row, row, row])
    digest = hashlib.sha256(payload).hexdigest()
    hashes = []
    for _ in range(2):
        dc._ANOMALIES = []
        dc._parse_reconciled_zip(payload, "data/spot/daily/klines/USDPUSDT/1d/USDPUSDT-1d-2026-07-17.zip", digest)
        hashes.append(dc._ANOMALIES[0]["resolution_sha256"])
    assert hashes[0] == hashes[1]


def test_gap_report_rejects_internal_calendar_gap(tmp_path):
    market_dir = tmp_path / "market"
    market_dir.mkdir()
    frame = pd.DataFrame({
        "timestamp": ["2026-01-01T00:00:00+00:00", "2026-01-03T00:00:00+00:00"],
        "close": [1.0, 1.1],
    })
    frame.to_csv(market_dir / "AAAUSDT__E01.csv", index=False)
    manifest = {"markets": [{"market_id": "AAAUSDT__E01"}]}
    report = dc._gap_report(tmp_path, manifest)
    assert report["unresolved_gap_count"] == 1
    assert report["events"][0]["type"] == "INTERNAL_CALENDAR_GAP"


def test_checksum_report_requires_64_hex_length_evidence():
    manifest = {
        "archive_count": 1,
        "archives": [{"key": "x", "sha256": "bad", "source_mode": "MONTHLY_CHECKSUM_VERIFIED"}],
        "reconstructions": [],
    }
    report = dc._checksum_report(manifest)
    assert report["all_source_checksums_verified"] is False
    assert report["invalid_checksum_evidence_count"] == 1
