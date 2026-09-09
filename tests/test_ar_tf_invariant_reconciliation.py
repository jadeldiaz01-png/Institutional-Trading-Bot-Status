import pandas as pd

import ar_tf.dataset_certifier as dc


def _market_frame(*, high=1.1, close=1.0, volume=100.0):
    return pd.DataFrame([{
        "timestamp": pd.Timestamp("2020-11-13T00:00:00Z"),
        "symbol": "AUDUSDT",
        "episode_id": 1,
        "open": 1.0,
        "high": high,
        "low": 0.9,
        "close": close,
        "volume": volume,
        "quote_volume": 1000.0,
        "trade_count": 10,
    }])


def _manifest(path):
    return {
        "dataset_sha256": "0" * 64,
        "market_manifest_sha256": "0" * 64,
        "markets": [{
            "market_id": "AUDUSDT__E01",
            "symbol": "AUDUSDT",
            "episode_id": 1,
            "rows": 1,
            "first_timestamp": "2020-11-13T00:00:00+00:00",
            "last_timestamp": "2020-11-13T00:00:00+00:00",
            "max_calendar_gap_days": 0,
            "csv_sha256": dc.file_sha256(path),
            "source_archive_count": 1,
        }],
        "archives": [],
        "archive_count": 0,
        "reconstructions": [],
        "internal_gap_repairs": [],
    }


def test_high_invariant_is_detected():
    row = _market_frame(high=0.95, close=1.0).iloc[0]
    assert dc._market_row_invariant_reasons(row) == ["HIGH_INVARIANT"]


def test_negative_activity_is_detected():
    row = _market_frame(volume=-1.0).iloc[0]
    assert dc._market_row_invariant_reasons(row) == ["NEGATIVE_ACTIVITY"]


def test_invalid_monthly_row_can_only_be_replaced_by_valid_same_day_verified_daily(monkeypatch, tmp_path):
    market_dir = tmp_path / "market"
    market_dir.mkdir()
    path = market_dir / "AUDUSDT__E01.csv"
    bad = _market_frame(high=0.95, close=1.0)
    bad.to_csv(path, index=False, lineterminator="\n")
    manifest = _manifest(path)
    old_dataset_sha = manifest["dataset_sha256"]

    verified = _market_frame(high=1.2, close=1.0)[[
        "timestamp", "open", "high", "low", "close", "volume", "quote_volume", "trade_count"
    ]]

    def fake_download(key, *, timeout=60):
        assert key == "data/spot/daily/klines/AUDUSDT/1d/AUDUSDT-1d-2020-11-13.zip"
        return verified.copy(), "a" * 64

    monkeypatch.setattr(dc, "_download_reconciled_zip", fake_download)
    dc._ANOMALIES = []
    result = dc._reconcile_market_invariants_from_daily(tmp_path, manifest)

    repaired = pd.read_csv(path)
    assert float(repaired.loc[0, "high"]) == 1.2
    assert result["row_reconciliation_attempt_count"] == 1
    assert result["row_reconciliation_resolved_count"] == 1
    assert result["dataset_sha256"] != old_dataset_sha
    assert dc._ANOMALIES[-1]["state"] == "RESOLVED"
    assert dc._ANOMALIES[-1]["source_sha256"] == "a" * 64


def test_invalid_daily_candidate_remains_unresolved_and_does_not_mutate_market(monkeypatch, tmp_path):
    market_dir = tmp_path / "market"
    market_dir.mkdir()
    path = market_dir / "AUDUSDT__E01.csv"
    bad = _market_frame(high=0.95, close=1.0)
    bad.to_csv(path, index=False, lineterminator="\n")
    manifest = _manifest(path)
    before_sha = dc.file_sha256(path)

    still_bad = _market_frame(high=0.94, close=1.0)[[
        "timestamp", "open", "high", "low", "close", "volume", "quote_volume", "trade_count"
    ]]

    monkeypatch.setattr(
        dc,
        "_download_reconciled_zip",
        lambda key, timeout=60: (still_bad.copy(), "b" * 64),
    )
    dc._ANOMALIES = []
    result = dc._reconcile_market_invariants_from_daily(tmp_path, manifest)

    assert dc.file_sha256(path) == before_sha
    assert result["row_reconciliation_attempt_count"] == 1
    assert result["row_reconciliation_resolved_count"] == 0
    assert dc._ANOMALIES[-1]["state"] == "UNRESOLVED"
    assert dc._ANOMALIES[-1]["resolution"] == "DAILY_ARCHIVE_INVARIANT_FAILED_FAIL_CLOSED"


def test_missing_daily_source_remains_unresolved(monkeypatch, tmp_path):
    market_dir = tmp_path / "market"
    market_dir.mkdir()
    path = market_dir / "AUDUSDT__E01.csv"
    _market_frame(high=0.95, close=1.0).to_csv(path, index=False, lineterminator="\n")
    manifest = _manifest(path)

    def missing(key, *, timeout=60):
        raise FileNotFoundError(key)

    monkeypatch.setattr(dc, "_download_reconciled_zip", missing)
    dc._ANOMALIES = []
    dc._reconcile_market_invariants_from_daily(tmp_path, manifest)

    assert dc._ANOMALIES[-1]["state"] == "UNRESOLVED"
    assert dc._ANOMALIES[-1]["resolution"] == "DAILY_ARCHIVE_RECONCILIATION_FAILED_FAIL_CLOSED"
