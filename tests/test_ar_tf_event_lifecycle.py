from ar_tf.event_lifecycle import apply_identity_break_registry
from ar_tf.lifecycle_verifier import VerifiedLifecycle


def _row(symbol: str = "BNXUSDT") -> VerifiedLifecycle:
    return VerifiedLifecycle(
        symbol=symbol,
        listed_at="2022-01-01T00:00:00+00:00",
        delisted_at=None,
        listing_evidence_url="https://data.binance.vision/first.zip",
        delisting_evidence_url="",
        listing_status="VERIFIED",
        delisting_status="NOT_APPLICABLE",
        active_currently=True,
        first_archive_month="2022-01",
        last_archive_month="2026-08",
        archive_month_count=56,
        archive_months_contiguous=True,
        first_boundary_zip_sha256="a" * 64,
        last_boundary_zip_sha256="b" * 64,
    )


def _registry(previous="2023-02-16T00:00:00+00:00", current="2023-02-22T00:00:00+00:00"):
    return {
        "schema_version": "1.0.0",
        "policy": {
            "identity_break_must_split_lifecycle": True,
            "same_identity_halt_may_resolve_gap": True,
            "unknown_event_fails_closed": True,
            "imputation_allowed": False,
        },
        "events": [{
            "market_id": "BNXUSDT__E01",
            "previous": previous,
            "current": current,
            "classification": "TOKEN_SWAP_REDENOMINATION_IDENTITY_BREAK",
            "source": "https://www.binance.com/official-event",
            "source_authority": "BINANCE_OFFICIAL",
            "requires_episode_split": True,
        }],
    }


def test_same_month_identity_break_creates_two_non_overlapping_episodes():
    out = apply_identity_break_registry([_row()], _registry())
    assert len(out) == 2
    old, new = out
    assert old.episode_id == 1 and new.episode_id == 2
    assert old.episode_count == 2 and new.episode_count == 2
    assert old.delisted_at == "2023-02-16T00:00:00+00:00"
    assert old.last_archive_month == "2023-01"
    assert new.first_archive_month == "2023-02"
    assert new.listed_at == "2023-02-22T00:00:00+00:00"
    assert old.active_currently is False
    assert new.active_currently is True
    assert "SAME_MONTH_PREBREAK_PARTIAL_DROPPED=true" in old.evidence_method


def test_cross_month_identity_break_keeps_distinct_boundary_months():
    reg = _registry("2023-03-29T00:00:00+00:00", "2023-04-02T00:00:00+00:00")
    out = apply_identity_break_registry([_row()], reg)
    old, new = out
    assert old.last_archive_month == "2023-03"
    assert new.first_archive_month == "2023-04"


def test_non_authoritative_identity_break_is_not_applied():
    reg = _registry()
    reg["events"][0]["source_authority"] = "SECONDARY"
    out = apply_identity_break_registry([_row()], reg)
    assert len(out) == 1
    assert out[0].episode_count == 1


def test_authoritative_terminal_event_truncates_orphan_rows_without_new_episode():
    row = _row("BCCUSDT")
    row = VerifiedLifecycle(**{**row.__dict__, "listed_at": "2017-11-01T00:00:00+00:00"})
    reg = {
        "schema_version": "1.0.0",
        "policy": {
            "identity_break_must_split_lifecycle": True,
            "same_identity_halt_may_resolve_gap": True,
            "unknown_event_fails_closed": True,
            "imputation_allowed": False,
        },
        "events": [{
            "market_id": "BCCUSDT__E01",
            "previous": "2018-11-15T00:00:00+00:00",
            "current": "2018-11-20T00:00:00+00:00",
            "classification": "HARD_FORK_TERMINAL_TICKER_IDENTITY_BREAK",
            "source": "https://support.binance.com/official-bcc-fork",
            "source_authority": "BINANCE_OFFICIAL",
            "requires_episode_split": False,
            "terminal_truncate": True,
        }],
    }
    out = apply_identity_break_registry([row], reg)
    assert len(out) == 1
    terminal = out[0]
    assert terminal.delisted_at == "2018-11-15T00:00:00+00:00"
    assert terminal.last_archive_month == "2018-11"
    assert terminal.active_currently is False
    assert terminal.episode_count == 1
    assert "BINANCE_OFFICIAL_TERMINAL_EVENT" in terminal.evidence_method
