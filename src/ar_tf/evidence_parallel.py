from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from .evidence_acquisition import MONTHLY_PREFIX, LifecycleCandidate, discover_historical_usdt_symbols, list_binance_vision_keys
from .lifecycle_verifier import VerifiedLifecycle, _boundary_times, _zip_url, current_spot_symbols, months_contiguous


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


def verify_candidates_parallel(
    candidates: list[LifecycleCandidate],
    months_by_symbol: dict[str, list[str]],
    *,
    timeout: int = 60,
    workers: int = 16,
) -> tuple[list[VerifiedLifecycle], list[dict]]:
    active = current_spot_symbols(timeout)

    def verify(candidate: LifecycleCandidate) -> tuple[VerifiedLifecycle | None, dict | None]:
        months = sorted(set(months_by_symbol.get(candidate.symbol, [])))
        if not months or not months_contiguous(months):
            return None, {"symbol": candidate.symbol, "reason": "ARCHIVE_MONTH_GAP", "months": months}
        try:
            first_open, _, first_digest = _boundary_times(candidate.symbol, months[0], timeout)
            _, last_close, last_digest = _boundary_times(candidate.symbol, months[-1], timeout)
        except Exception as exc:
            return None, {"symbol": candidate.symbol, "reason": "BOUNDARY_VERIFICATION_FAILED", "detail": str(exc)}
        is_active = candidate.symbol in active
        return VerifiedLifecycle(
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
        ), None

    verified: list[VerifiedLifecycle] = []
    rejected: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(verify, candidate) for candidate in candidates]
        for future in as_completed(futures):
            row, rejection = future.result()
            if row is not None:
                verified.append(row)
            if rejection is not None:
                rejected.append(rejection)
    verified.sort(key=lambda x: x.symbol)
    rejected.sort(key=lambda x: (x.get("symbol", ""), x.get("reason", "")))
    return verified, rejected
