from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .ingestion import build_manifest, download_month, load_lifecycle_csv, write_manifest


def month_starts(start: pd.Timestamp, end: pd.Timestamp):
    cur = pd.Timestamp(year=start.year, month=start.month, day=1, tz="UTC")
    stop = pd.Timestamp(year=end.year, month=end.month, day=1, tz="UTC")
    while cur <= stop:
        yield cur
        cur = cur + pd.offsets.MonthBegin(1)


def _overlaps(lifecycle, start: pd.Timestamp, end: pd.Timestamp) -> bool:
    return lifecycle.listed_at < end and (lifecycle.delisted_at is None or lifecycle.delisted_at > start)


def download_history(lifecycle_csv: str, start: str, end: str, output_dir: str, interval: str = "1d") -> dict:
    lifecycles = load_lifecycle_csv(lifecycle_csv)
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    start_ts = start_ts.tz_localize("UTC") if start_ts.tzinfo is None else start_ts.tz_convert("UTC")
    end_ts = end_ts.tz_localize("UTC") if end_ts.tzinfo is None else end_ts.tz_convert("UTC")
    if end_ts <= start_ts:
        raise ValueError("end must be after start")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    by_symbol: dict[str, list[pd.DataFrame]] = {s: [] for s in lifecycles}
    acquisition = []

    for month in month_starts(start_ts, end_ts):
        month_end = month + pd.offsets.MonthBegin(1)
        universe = {s for s, lifecycle in lifecycles.items() if _overlaps(lifecycle, month, month_end)}
        for symbol in sorted(universe):
            lifecycle = lifecycles[symbol]
            frame = download_month(symbol, interval, month.year, month.month)
            # A listing/delisting can occur mid-month. Fetch based on interval overlap,
            # then filter rows to the exact lifecycle window; month-start eligibility
            # alone would silently omit mid-month listings.
            if not frame.empty:
                frame = frame[frame.index >= lifecycle.listed_at]
                if lifecycle.delisted_at is not None:
                    frame = frame[frame.index < lifecycle.delisted_at]
            acquisition.append({"symbol": symbol, "month": month.strftime("%Y-%m"), "rows": int(len(frame))})
            if not frame.empty:
                by_symbol[symbol].append(frame)

    frames: dict[str, pd.DataFrame] = {}
    for symbol, chunks in by_symbol.items():
        if not chunks:
            continue
        frame = pd.concat(chunks).sort_index()
        frame = frame[~frame.index.duplicated(keep="first")]
        frame = frame[(frame.index >= start_ts) & (frame.index <= end_ts)]
        frames[symbol] = frame
        frame.reset_index(names="timestamp").to_csv(out / f"{symbol}.csv", index=False)

    manifest = build_manifest(frames, "https://data.binance.vision spot monthly klines", lifecycle_csv)
    manifest["requested_start"] = start_ts.isoformat()
    manifest["requested_end"] = end_ts.isoformat()
    manifest["interval"] = interval
    manifest["acquisition_log"] = acquisition
    write_manifest(manifest, out / "dataset-manifest.json")
    return manifest


def main() -> None:
    p = argparse.ArgumentParser(description="Research-only Binance Vision downloader")
    p.add_argument("--lifecycle", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--output-dir", default="data/ar_tf_v1")
    p.add_argument("--interval", default="1d")
    args = p.parse_args()
    manifest = download_history(args.lifecycle, args.start, args.end, args.output_dir, args.interval)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
