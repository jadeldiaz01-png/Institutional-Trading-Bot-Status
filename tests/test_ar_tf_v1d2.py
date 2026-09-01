import pandas as pd

from ar_tf.evidence_acquisition import (
    canonical_sha256,
    extract_usdt_daily_observations,
    lifecycle_candidates,
    validate_verified_lifecycle,
)


def test_extracts_only_usdt_daily_archives():
    keys = [
        "data/spot/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2020-01.zip",
        "data/spot/monthly/klines/ETHBTC/1d/ETHBTC-1d-2020-01.zip",
        "data/spot/monthly/klines/ETHUSDT/1h/ETHUSDT-1h-2020-01.zip",
        "data/spot/monthly/klines/ETHUSDT/1d/ETHUSDT-1d-2020-02.zip",
    ]
    obs = extract_usdt_daily_observations(keys)
    assert [(x.symbol, x.month) for x in obs] == [("BTCUSDT", "2020-01"), ("ETHUSDT", "2020-02")]


def test_lifecycle_candidate_is_not_marked_verified():
    keys = [
        "data/spot/monthly/klines/OLDUSDT/1d/OLDUSDT-1d-2020-01.zip",
        "data/spot/monthly/klines/OLDUSDT/1d/OLDUSDT-1d-2020-02.zip",
    ]
    candidate = lifecycle_candidates(extract_usdt_daily_observations(keys))[0]
    assert candidate.first_archive_month == "2020-01"
    assert candidate.last_archive_month == "2020-02"
    assert candidate.verification_status == "BOUNDARY_CANDIDATE_ONLY"


def test_provenance_hash_is_order_stable_for_mappings():
    assert canonical_sha256({"a": 1, "b": 2}) == canonical_sha256({"b": 2, "a": 1})


def test_unverified_lifecycle_fails_closed():
    rows = pd.DataFrame([
        {
            "symbol": "OLDUSDT",
            "listed_at": "2020-01-02T00:00:00Z",
            "delisted_at": "2021-03-01T00:00:00Z",
            "listing_evidence_url": "https://data.binance.vision/example",
            "delisting_evidence_url": "https://www.binance.com/example",
            "listing_status": "VERIFIED",
            "delisting_status": "INFERRED",
        }
    ])
    reasons = validate_verified_lifecycle(rows)
    assert "OLDUSDT:DELISTING_BOUNDARY_UNVERIFIED" in reasons


def test_verified_lifecycle_can_unlock_historical_download_only():
    rows = pd.DataFrame([
        {
            "symbol": "BTCUSDT",
            "listed_at": "2017-08-17T00:00:00Z",
            "delisted_at": None,
            "listing_evidence_url": "https://data.binance.vision/example",
            "delisting_evidence_url": "",
            "listing_status": "VERIFIED",
            "delisting_status": "NOT_APPLICABLE",
        }
    ])
    assert validate_verified_lifecycle(rows) == []
