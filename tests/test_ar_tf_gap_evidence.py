import json

from ar_tf.gap_evidence import classify_gap_report


def _registry():
    return {
        "schema_version": "1.0.0",
        "policy": {
            "same_identity_halt_may_resolve_gap": True,
            "identity_break_must_split_lifecycle": True,
            "unknown_event_fails_closed": True,
            "imputation_allowed": False,
        },
        "events": [
            {
                "market_id": "AEURUSDT__E01",
                "previous": "2023-12-05T00:00:00+00:00",
                "current": "2023-12-08T00:00:00+00:00",
                "classification": "SAME_IDENTITY_TRADING_HALT",
                "resolution": "EXPECTED_NO_TRADING_INTERVAL",
                "source": "https://www.binance.com/example-aeur",
                "source_authority": "BINANCE_OFFICIAL",
                "evidence": "halt",
                "requires_episode_split": False,
            },
            {
                "market_id": "BNXUSDT__E01",
                "previous": "2023-02-16T00:00:00+00:00",
                "current": "2023-02-22T00:00:00+00:00",
                "classification": "TOKEN_SWAP_REDENOMINATION_IDENTITY_BREAK",
                "resolution": "SPLIT_LIFECYCLE_EPISODE",
                "source": "https://www.binance.com/example-bnx",
                "source_authority": "BINANCE_OFFICIAL",
                "evidence": "1:100",
                "requires_episode_split": True,
            },
        ],
    }


def test_same_identity_halt_can_resolve_exact_gap():
    gaps = {"events": [{
        "market_id": "AEURUSDT__E01",
        "type": "INTERNAL_CALENDAR_GAP",
        "previous": "2023-12-05T00:00:00+00:00",
        "current": "2023-12-08T00:00:00+00:00",
        "gap_days": 3,
    }]}
    report = classify_gap_report(gaps, _registry())
    assert report["resolved_gap_count"] == 1
    assert report["unresolved_gap_count"] == 0
    assert report["all_gaps_resolved"] is True


def test_identity_break_never_resolves_by_whitelisting_gap():
    gaps = {"events": [{
        "market_id": "BNXUSDT__E01",
        "type": "INTERNAL_CALENDAR_GAP",
        "previous": "2023-02-16T00:00:00+00:00",
        "current": "2023-02-22T00:00:00+00:00",
        "gap_days": 6,
    }]}
    report = classify_gap_report(gaps, _registry())
    assert report["unresolved_gap_count"] == 1
    assert report["identity_break_count"] == 1
    assert report["events"][0]["resolution"] == "SPLIT_LIFECYCLE_EPISODE"


def test_unknown_gap_fails_closed():
    gaps = {"events": [{
        "market_id": "UNKNOWNUSDT__E01",
        "type": "INTERNAL_CALENDAR_GAP",
        "previous": "2026-01-01T00:00:00+00:00",
        "current": "2026-01-03T00:00:00+00:00",
        "gap_days": 2,
    }]}
    report = classify_gap_report(gaps, _registry())
    assert report["unresolved_gap_count"] == 1
    assert report["events"][0]["classification"] == "UNKNOWN_EVENT"


def test_report_hash_is_deterministic():
    gaps = {"events": []}
    first = classify_gap_report(gaps, _registry())
    second = classify_gap_report(gaps, _registry())
    assert first["report_sha256"] == second["report_sha256"]
