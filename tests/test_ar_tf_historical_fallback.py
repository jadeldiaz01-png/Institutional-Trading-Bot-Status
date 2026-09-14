import pandas as pd
import pytest

import ar_tf.historical_dataset as hd


def _row(day: str) -> pd.DataFrame:
    ts = pd.Timestamp(day, tz="UTC")
    return pd.DataFrame({
        "timestamp": [ts],
        "open": [1.0],
        "high": [1.1],
        "low": [0.9],
        "close": [1.0],
        "volume": [100.0],
        "quote_volume": [1000.0],
        "trade_count": [10],
    })


def _daily_key(symbol: str, day: str) -> str:
    return f"data/spot/daily/klines/{symbol}/1d/{symbol}-1d-{day}.zip"


def test_daily_fallback_reconstructs_exact_expected_days(monkeypatch):
    keys = [_daily_key("AXSUSDT", f"2026-02-{d:02d}") for d in range(1, 29)]
    monkeypatch.setattr(hd, "list_binance_vision_keys", lambda prefix, timeout=60: keys)

    def fake_download(key, timeout=60):
        day = key.rsplit("-", 3)[-3] + "-" + key.rsplit("-", 3)[-2] + "-" + key.rsplit("-", 3)[-1].replace(".zip", "")
        return _row(day), "a" * 64

    monkeypatch.setattr(hd, "_download_verified_zip", fake_download)
    frame, digest, sources = hd.reconstruct_month_from_daily(
        "AXSUSDT", "2026-02",
        expected_start=pd.Timestamp("2026-02-01", tz="UTC"),
        expected_end=pd.Timestamp("2026-02-28", tz="UTC"),
    )
    assert len(frame) == 28
    assert len(sources) == 28
    assert len(digest) == 64
    assert frame["timestamp"].is_monotonic_increasing


def test_daily_fallback_rejects_missing_calendar_day(monkeypatch):
    keys = [_daily_key("UMAUSDT", f"2026-07-{d:02d}") for d in range(1, 32) if d != 15]
    monkeypatch.setattr(hd, "list_binance_vision_keys", lambda prefix, timeout=60: keys)

    def fake_download(key, timeout=60):
        day = key.rsplit("/", 1)[-1].replace("UMAUSDT-1d-", "").replace(".zip", "")
        return _row(day), "b" * 64

    monkeypatch.setattr(hd, "_download_verified_zip", fake_download)
    with pytest.raises(ValueError, match="coverage mismatch"):
        hd.reconstruct_month_from_daily(
            "UMAUSDT", "2026-07",
            expected_start=pd.Timestamp("2026-07-01", tz="UTC"),
            expected_end=pd.Timestamp("2026-07-31", tz="UTC"),
        )


def test_daily_fallback_supports_partial_delisting_month(monkeypatch):
    keys = [_daily_key("KLAYUSDT", f"2024-10-{d:02d}") for d in range(1, 29)]
    monkeypatch.setattr(hd, "list_binance_vision_keys", lambda prefix, timeout=60: keys)

    def fake_download(key, timeout=60):
        day = key.rsplit("/", 1)[-1].replace("KLAYUSDT-1d-", "").replace(".zip", "")
        return _row(day), "c" * 64

    monkeypatch.setattr(hd, "_download_verified_zip", fake_download)
    frame, _, sources = hd.reconstruct_month_from_daily(
        "KLAYUSDT", "2024-10",
        expected_start=pd.Timestamp("2024-10-01", tz="UTC"),
        expected_end=pd.Timestamp("2024-10-28", tz="UTC"),
    )
    assert frame["timestamp"].iloc[-1] == pd.Timestamp("2024-10-28", tz="UTC")
    assert len(sources) == 28


def test_expected_bounds_use_lifecycle_boundary_dates():
    start, end = hd._expected_daily_bounds(
        "2024-10", "2024-10-05T12:00:00+00:00", "2024-10-28T23:59:59+00:00"
    )
    assert start == pd.Timestamp("2024-10-05", tz="UTC")
    assert end == pd.Timestamp("2024-10-28", tz="UTC")


def test_internal_gap_recovery_requires_exact_checksum_verified_coverage(monkeypatch):
    monthly = pd.concat([_row("2022-09-11"), _row("2022-09-15")], ignore_index=True)

    def fake_download(key, timeout=60):
        day = key.rsplit("/", 1)[-1].replace("NBTUSDT-1d-", "").replace(".zip", "")
        return _row(day), "d" * 64

    monkeypatch.setattr(hd, "_download_verified_zip", fake_download)
    repaired, ledger = hd.recover_internal_gaps_from_daily(monthly, "NBTUSDT")

    assert list(repaired["timestamp"]) == list(pd.date_range("2022-09-11", "2022-09-15", freq="D", tz="UTC"))
    assert len(ledger) == 1
    assert ledger[0]["state"] == "RESOLVED"
    assert ledger[0]["resolution"] == "DAILY_CHECKSUM_VERIFIED_MONTH_COVERAGE_RECOVERY"
    assert ledger[0]["recovered_day_count"] == 3
    assert len(ledger[0]["sources"]) == 3
    assert len(ledger[0]["sources_sha256"]) == 64


def test_internal_gap_recovery_is_atomic_when_any_daily_archive_is_missing(monkeypatch):
    monthly = pd.concat([_row("2022-09-11"), _row("2022-09-15")], ignore_index=True)

    def fake_download(key, timeout=60):
        day = key.rsplit("/", 1)[-1].replace("NBTUSDT-1d-", "").replace(".zip", "")
        if day == "2022-09-13":
            raise FileNotFoundError("official daily archive absent")
        return _row(day), "e" * 64

    monkeypatch.setattr(hd, "_download_verified_zip", fake_download)
    repaired, ledger = hd.recover_internal_gaps_from_daily(monthly, "NBTUSDT")

    assert list(repaired["timestamp"]) == [
        pd.Timestamp("2022-09-11", tz="UTC"),
        pd.Timestamp("2022-09-15", tz="UTC"),
    ]
    assert len(ledger) == 1
    assert ledger[0]["state"] == "UNRESOLVED"
    assert ledger[0]["resolution"] == "DAILY_ARCHIVE_COVERAGE_INCOMPLETE_FAIL_CLOSED"
    assert any("2022-09-13" in entry["key"] for entry in ledger[0]["errors"])


def test_trailing_month_gap_recovery_handles_cross_month_next_observation(monkeypatch):
    monthly = _row("2022-09-11")

    def fake_download(key, timeout=60):
        day = key.rsplit("/", 1)[-1].replace("NBTUSDT-1d-", "").replace(".zip", "")
        return _row(day), "f" * 64

    monkeypatch.setattr(hd, "_download_verified_zip", fake_download)
    repaired, ledger = hd.recover_internal_gaps_from_daily(
        monthly,
        "NBTUSDT",
        expected_start=pd.Timestamp("2022-09-01", tz="UTC"),
        expected_end=pd.Timestamp("2022-09-30", tz="UTC"),
    )

    # This test focuses on the trailing gap that previously escaped detection.
    # Leading days are also lifecycle-bounded candidates and therefore recovered.
    assert repaired["timestamp"].min() == pd.Timestamp("2022-09-01", tz="UTC")
    assert repaired["timestamp"].max() == pd.Timestamp("2022-09-30", tz="UTC")
    assert len(repaired) == 30
    assert any(
        entry["state"] == "RESOLVED"
        and "2022-09-12" in entry["missing_days"]
        and "2022-09-30" in entry["missing_days"]
        for entry in ledger
    )
