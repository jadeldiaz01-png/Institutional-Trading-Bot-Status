import json
from pathlib import Path

import pytest

from ar_tf.event_lifecycle import apply_identity_break_registry
from ar_tf.lifecycle_verifier import VerifiedLifecycle


REGISTRY_PATH = Path("config/ar_tf_market_event_registry_2026.json")


def _row(symbol: str, listed_at: str, delisted_at: str, first_month: str, last_month: str) -> VerifiedLifecycle:
    start_year, start_month = map(int, first_month.split("-"))
    end_year, end_month = map(int, last_month.split("-"))
    archive_month_count = (end_year - start_year) * 12 + end_month - start_month + 1
    return VerifiedLifecycle(
        symbol=symbol,
        listed_at=listed_at,
        delisted_at=delisted_at,
        listing_evidence_url="https://data.binance.vision/first.zip",
        delisting_evidence_url="https://data.binance.vision/last.zip",
        listing_status="VERIFIED",
        delisting_status="VERIFIED",
        active_currently=False,
        first_archive_month=first_month,
        last_archive_month=last_month,
        archive_month_count=archive_month_count,
        archive_months_contiguous=True,
        first_boundary_zip_sha256="a" * 64,
        last_boundary_zip_sha256="b" * 64,
    )


def _registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _isolated_registry(registry: dict, market_id: str) -> dict:
    return {
        "schema_version": registry["schema_version"],
        "policy": dict(registry["policy"]),
        "events": [event for event in registry["events"] if event["market_id"] == market_id],
    }


@pytest.mark.parametrize(
    ("symbol", "previous", "current", "ratio_marker", "listed_at", "delisted_at", "first_month", "last_month"),
    [
        (
            "BTCSTUSDT",
            "2021-03-15T00:00:00+00:00",
            "2021-03-19T00:00:00+00:00",
            "1:10",
            "2021-01-13T00:00:00+00:00",
            "2022-11-28T00:00:00+00:00",
            "2021-01",
            "2022-11",
        ),
        (
            "COCOSUSDT",
            "2021-01-19T00:00:00+00:00",
            "2021-01-23T00:00:00+00:00",
            "1000:1",
            "2019-08-21T00:00:00+00:00",
            "2023-05-29T00:00:00+00:00",
            "2019-08",
            "2023-05",
        ),
    ],
)
def test_issuer_authoritative_redenomination_splits_same_ticker_lifecycle(
    symbol,
    previous,
    current,
    ratio_marker,
    listed_at,
    delisted_at,
    first_month,
    last_month,
):
    registry = _registry()
    market_id = f"{symbol}__E01"
    events = [event for event in registry["events"] if event["market_id"] == market_id]
    assert len(events) == 1
    event = events[0]
    assert event["previous"] == previous
    assert event["current"] == current
    assert event["source_authority"] == "TOKEN_ISSUER_OFFICIAL"
    assert event["identity_event_source"] == event["source"]
    assert event["observed_gap_boundary_source"] == "BINANCE_VISION_CHECKSUM_VERIFIED_1D"
    assert event["requires_episode_split"] is True
    assert event["resolution"] == "SPLIT_LIFECYCLE_EPISODE"
    assert ratio_marker in event["evidence"]

    out = apply_identity_break_registry(
        [_row(symbol, listed_at, delisted_at, first_month, last_month)],
        _isolated_registry(registry, market_id),
    )
    assert len(out) == 2
    old, new = out
    assert old.episode_id == 1 and new.episode_id == 2
    assert old.episode_count == 2 and new.episode_count == 2
    assert old.delisted_at == previous
    assert new.listed_at == current
    assert old.last_archive_month < new.first_archive_month
    assert "TOKEN_ISSUER_OFFICIAL_IDENTITY_BREAK" in old.evidence_method
    assert "SAME_MONTH_PREBREAK_PARTIAL_DROPPED=true" in old.evidence_method
    assert "SAME_MONTH_PREBREAK_PARTIAL_DROPPED=true" in new.evidence_method


def test_token_issuer_cannot_authorize_exchange_halt_or_unsplit_event():
    registry = _registry()
    bad = {
        "schema_version": registry["schema_version"],
        "policy": dict(registry["policy"]),
        "events": [{
            "market_id": "BTCSTUSDT__E01",
            "previous": "2021-03-15T00:00:00+00:00",
            "current": "2021-03-19T00:00:00+00:00",
            "classification": "SAME_IDENTITY_TRADING_HALT",
            "resolution": "EXPECTED_NO_TRADING_INTERVAL",
            "source": "https://btcst.medium.com/official",
            "identity_event_source": "https://btcst.medium.com/official",
            "source_authority": "TOKEN_ISSUER_OFFICIAL",
            "requires_episode_split": False,
        }],
    }
    row = _row(
        "BTCSTUSDT", "2021-01-13T00:00:00+00:00", "2022-11-28T00:00:00+00:00", "2021-01", "2022-11"
    )
    out = apply_identity_break_registry([row], bad)
    assert len(out) == 1
    assert out[0].episode_count == 1
    assert out[0].listed_at == row.listed_at
    assert out[0].delisted_at == row.delisted_at


def test_registry_still_forbids_imputation_and_unknown_event_assumption():
    policy = _registry()["policy"]
    assert policy["imputation_allowed"] is False
    assert policy["unknown_event_fails_closed"] is True
    assert policy["identity_break_must_split_lifecycle"] is True
