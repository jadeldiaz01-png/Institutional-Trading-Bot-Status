from __future__ import annotations

from dataclasses import replace
from typing import Iterable

import pandas as pd

from .evidence_acquisition import canonical_sha256
from .lifecycle_verifier import VerifiedLifecycle


def _symbol_from_market_id(market_id: str) -> str:
    if "__E" not in market_id:
        raise ValueError(f"invalid market_id: {market_id}")
    return market_id.split("__E", 1)[0]


def _month_count(start: pd.Timestamp, end: pd.Timestamp) -> int:
    return (end.year - start.year) * 12 + end.month - start.month + 1


def _ts(value: str | pd.Timestamp) -> pd.Timestamp:
    out = pd.Timestamp(value)
    return out.tz_localize("UTC") if out.tzinfo is None else out.tz_convert("UTC")


def apply_identity_break_registry(
    rows: Iterable[VerifiedLifecycle],
    registry: dict,
) -> list[VerifiedLifecycle]:
    """Split verified tradability episodes at authoritative identity breaks.

    This never price-adjusts across a redenomination/fork/ticker reuse and never
    creates synthetic candles. The last pre-break candle and first post-break
    candle become terminal/initial boundaries of distinct market episodes.
    Only exact BINANCE_OFFICIAL registry events marked requires_episode_split
    are eligible. Unknown or non-authoritative events are ignored here and
    remain blocking later in the gap certifier.
    """
    policy = registry.get("policy", {})
    if policy.get("identity_break_must_split_lifecycle") is not True:
        raise ValueError("registry must require lifecycle split for identity breaks")
    if policy.get("imputation_allowed") is not False:
        raise ValueError("registry must forbid imputation")

    registry_sha = canonical_sha256(registry)
    current = list(rows)

    split_events = [
        event for event in registry.get("events", [])
        if event.get("requires_episode_split") is True
        and event.get("source_authority") == "BINANCE_OFFICIAL"
    ]
    split_events.sort(key=lambda e: (_symbol_from_market_id(str(e["market_id"])), str(e["current"])))

    for event in split_events:
        symbol = _symbol_from_market_id(str(event["market_id"]))
        previous = _ts(str(event["previous"]))
        resumed = _ts(str(event["current"]))
        if resumed <= previous:
            raise ValueError(f"invalid identity-break ordering for {symbol}")

        candidates: list[tuple[int, VerifiedLifecycle]] = []
        for idx, row in enumerate(current):
            if row.symbol != symbol:
                continue
            start = _ts(row.listed_at)
            end = _ts(row.delisted_at) if row.delisted_at else pd.Timestamp.max.tz_localize("UTC")
            if start <= previous and resumed <= end:
                candidates.append((idx, row))
        if len(candidates) != 1:
            raise ValueError(
                f"identity break must match exactly one lifecycle episode: {symbol}: matches={len(candidates)}"
            )

        idx, row = candidates[0]
        old = replace(
            row,
            delisted_at=previous.isoformat(),
            delisting_evidence_url=str(event["source"]),
            delisting_status="VERIFIED",
            active_currently=False,
            last_archive_month=previous.strftime("%Y-%m"),
            archive_month_count=_month_count(_ts(row.listed_at), previous),
            evidence_method=(
                f"BINANCE_VISION_CHECKSUM_VERIFIED+BINANCE_OFFICIAL_IDENTITY_BREAK:"
                f"{event['classification']}:{registry_sha}"
            ),
        )
        new_end = _ts(row.delisted_at) if row.delisted_at else None
        new = replace(
            row,
            listed_at=resumed.isoformat(),
            listing_evidence_url=str(event["source"]),
            listing_status="VERIFIED",
            first_archive_month=resumed.strftime("%Y-%m"),
            last_archive_month=(new_end.strftime("%Y-%m") if new_end is not None else row.last_archive_month),
            archive_month_count=_month_count(resumed, new_end if new_end is not None else _ts(f"{row.last_archive_month}-01")),
            evidence_method=(
                f"BINANCE_VISION_CHECKSUM_VERIFIED+BINANCE_OFFICIAL_IDENTITY_BREAK:"
                f"{event['classification']}:{registry_sha}"
            ),
        )
        current[idx:idx + 1] = [old, new]

    # Renumber every symbol deterministically after all splits.
    by_symbol: dict[str, list[VerifiedLifecycle]] = {}
    for row in current:
        by_symbol.setdefault(row.symbol, []).append(row)

    result: list[VerifiedLifecycle] = []
    for symbol, symbol_rows in sorted(by_symbol.items()):
        symbol_rows.sort(key=lambda row: _ts(row.listed_at))
        count = len(symbol_rows)
        for episode_id, row in enumerate(symbol_rows, start=1):
            result.append(replace(row, episode_id=episode_id, episode_count=count))
    return result
