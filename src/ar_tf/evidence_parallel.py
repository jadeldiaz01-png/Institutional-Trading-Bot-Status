from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace

from .evidence_acquisition import MONTHLY_PREFIX, LifecycleCandidate, discover_historical_usdt_symbols, list_binance_vision_keys
from .lifecycle_verifier import VerifiedLifecycle, _boundary_times, _month_ordinal, _zip_url, current_spot_symbols


def acquire_usdt_daily_keys_parallel(*, timeout: int = 60, workers: int = 16) -> tuple[list[str], list[str]]:
    symbols = discover_historical_usdt_symbols(timeout=timeout)

    def fetch(symbol: str) -> list[str]:
        return list_binance_vision_keys(f"{MONTHLY_PREFIX}{symbol}/1d/", timeout=timeout)

    keys: list[str] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        future_to_symbol = {pool.submit(fetch, symbol): symbol for symbol in symbols}
        for future in as_completed(future_to_symbol):
            keys.extend(future.result())
    return sorted(set(symbols)), sorted(set(keys))


def split_tradability_episodes(months: list[str]) -> list[list[str]]:
    """Split archive history at gaps instead of silently joining disjoint lives."""
    ordered = sorted(set(months), key=_month_ordinal)
    episodes: list[list[str]] = []
    current: list[str] = []
    for month in ordered:
        if current and _month_ordinal(month) - _month_ordinal(current[-1]) > 1:
            episodes.append(current)
            current = []
        current.append(month)
    if current:
        episodes.append(current)
    return episodes


def verify_candidates_parallel(
    candidates: list[LifecycleCandidate],
    months_by_symbol: dict[str, list[str]],
    *,
    timeout: int = 60,
    workers: int = 16,
) -> tuple[list[VerifiedLifecycle], list[dict]]:
    """Verify every contiguous tradability episode for every historical ticker.

    A ticker can have multiple disjoint episodes due to suspensions, relistings,
    migrations, or ticker reuse. Those episodes must never be bridged with
    synthetic returns. Only the final episode can be considered currently active.
    """
    active = current_spot_symbols(timeout)
    tasks: list[tuple[LifecycleCandidate, int, list[str], int]] = []
    for candidate in candidates:
        episodes = split_tradability_episodes(months_by_symbol.get(candidate.symbol, []))
        for episode_number, episode_months in enumerate(episodes, start=1):
            tasks.append((candidate, episode_number, episode_months, len(episodes)))

    def verify(task: tuple[LifecycleCandidate, int, list[str], int]) -> tuple[VerifiedLifecycle | None, dict | None]:
        candidate, episode_number, months, episode_count = task
        if not months:
            return None, {"symbol": candidate.symbol, "episode_id": episode_number, "reason": "EMPTY_EPISODE"}
        try:
            first_open, _, first_digest = _boundary_times(candidate.symbol, months[0], timeout)
            _, last_close, last_digest = _boundary_times(candidate.symbol, months[-1], timeout)
        except Exception as exc:
            return None, {
                "symbol": candidate.symbol,
                "episode_id": episode_number,
                "reason": "BOUNDARY_VERIFICATION_FAILED",
                "detail": str(exc),
            }
        is_final_episode = episode_number == episode_count
        is_active = is_final_episode and candidate.symbol in active
        row = VerifiedLifecycle(
            symbol=candidate.symbol,
            listed_at=first_open.isoformat(),
            delisted_at=None if is_active else last_close.isoformat(),
            listing_evidence_url=_zip_url(candidate.symbol, months[0]),
            delisting_evidence_url="" if is_active else _zip_url(candidate.symbol, months[-1]),
            listing_status="VERIFIED",
            delisting_status="NOT_APPLICABLE" if is_active else "VERIFIED",
            active_currently=is_active,
            first_archive_month=months[0],
            last_archive_month=months[-1],
            archive_month_count=len(months),
            archive_months_contiguous=True,
            first_boundary_zip_sha256=first_digest,
            last_boundary_zip_sha256=last_digest,
            episode_id=episode_number,
            episode_count=episode_count,
        )
        return row, None

    verified: list[VerifiedLifecycle] = []
    rejected: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(verify, task) for task in tasks]
        for future in as_completed(futures):
            row, rejection = future.result()
            if row is not None:
                verified.append(row)
            if rejection is not None:
                rejected.append(rejection)
    verified.sort(key=lambda x: (x.symbol, x.episode_id))
    rejected.sort(key=lambda x: (x.get("symbol", ""), x.get("episode_id", 0), x.get("reason", "")))
    return verified, rejected
