"""Point-in-time normalization and feature construction for M0→M7 research.

Only public research evidence is consumed. Forward returns are labels and are never
used to construct features at the same decision timestamp.
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
import statistics
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SPOT_FILE_RE = re.compile(r"spot-klines-(?P<symbol>[A-Z0-9]+)-1h-(?P<day>\d{4}-\d{2}-\d{2})\.csv$")
DERIV_KLINE_RE = re.compile(r"coinm-klines-(?P<symbol>[A-Z0-9_]+)-1h-(?P<day>\d{4}-\d{2}-\d{2})\.csv$")
DERIV_METRICS_RE = re.compile(r"coinm-metrics-(?P<symbol>[A-Z0-9_]+)-(?P<day>\d{4}-\d{2}-\d{2})\.csv$")
ONCHAIN_RE = re.compile(r"coinmetrics-(?P<asset>[a-z0-9]+)-onchain(?:-[^.]+)?\.json$")


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _epoch_ms(value: Any) -> int:
    number = int(float(value))
    if number > 100_000_000_000_000:
        return number // 1000
    return number


def _iso_from_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _read_kline_csv(path: Path, symbol: str) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    has_header = bool(rows[0] and rows[0][0].strip().lower() == "open_time")
    data_rows = rows[1:] if has_header else rows

    out: list[dict[str, Any]] = []
    for raw in data_rows:
        if len(raw) < 11:
            raise ValueError(f"{path}: expected >=11 kline columns, got {len(raw)}")
        out.append(
            {
                "symbol": symbol,
                "open_time_ms": _epoch_ms(raw[0]),
                "close_time_ms": _epoch_ms(raw[6]),
                "open": float(raw[1]),
                "high": float(raw[2]),
                "low": float(raw[3]),
                "close": float(raw[4]),
                "volume": float(raw[5]),
                "quote_volume": float(raw[7]),
                "count": int(float(raw[8])),
                "taker_buy_volume": float(raw[9]),
                "taker_buy_quote_volume": float(raw[10]),
                "source_path": str(path),
            }
        )
    return out


def load_spot_bars(root: Path) -> dict[str, list[dict[str, Any]]]:
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in sorted(root.rglob("spot-klines-*-1h-*.csv")):
        match = SPOT_FILE_RE.search(path.name)
        if match:
            by_symbol[match.group("symbol")].extend(_read_kline_csv(path, match.group("symbol")))
    for symbol, rows in by_symbol.items():
        dedup = {int(row["close_time_ms"]): row for row in rows}
        by_symbol[symbol] = [dedup[key] for key in sorted(dedup)]
    return dict(by_symbol)


def load_derivative_bars(root: Path) -> dict[str, list[dict[str, Any]]]:
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in sorted(root.rglob("coinm-klines-*-1h-*.csv")):
        match = DERIV_KLINE_RE.search(path.name)
        if match:
            by_symbol[match.group("symbol")].extend(_read_kline_csv(path, match.group("symbol")))
    for symbol, rows in by_symbol.items():
        dedup = {int(row["close_time_ms"]): row for row in rows}
        by_symbol[symbol] = [dedup[key] for key in sorted(dedup)]
    return dict(by_symbol)


def load_derivative_metrics(root: Path) -> dict[str, list[dict[str, Any]]]:
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in sorted(root.rglob("coinm-metrics-*.csv")):
        match = DERIV_METRICS_RE.search(path.name)
        if not match:
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                created = datetime.strptime(row["create_time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                by_symbol[match.group("symbol")].append(
                    {
                        "timestamp_ms": int(created.timestamp() * 1000),
                        "sum_open_interest": _float(row.get("sum_open_interest")),
                        "sum_open_interest_value": _float(row.get("sum_open_interest_value")),
                        "toptrader_count_ratio": _float(row.get("count_toptrader_long_short_ratio")),
                        "toptrader_sum_ratio": _float(row.get("sum_toptrader_long_short_ratio")),
                        "global_long_short_ratio": _float(row.get("count_long_short_ratio")),
                        "taker_long_short_ratio": _float(row.get("sum_taker_long_short_vol_ratio")),
                        "source_path": str(path),
                    }
                )
    for symbol, rows in by_symbol.items():
        dedup = {int(row["timestamp_ms"]): row for row in rows}
        by_symbol[symbol] = [dedup[key] for key in sorted(dedup)]
    return dict(by_symbol)


def load_onchain(root: Path) -> dict[str, list[dict[str, Any]]]:
    by_asset: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in sorted(root.rglob("coinmetrics-*-onchain*.json")):
        match = ONCHAIN_RE.search(path.name)
        if not match:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload.get("data", []):
            ts_text = str(row["time"])
            normalized = re.sub(r"\.(\d{6})\d*Z$", r".\1+00:00", ts_text)
            if normalized.endswith("Z"):
                normalized = normalized[:-1] + "+00:00"
            ts = datetime.fromisoformat(normalized).astimezone(timezone.utc)
            available = ts + timedelta(days=1)
            by_asset[match.group("asset")].append(
                {
                    "metric_time_ms": int(ts.timestamp() * 1000),
                    "available_time_ms": int(available.timestamp() * 1000),
                    "AdrActCnt": _float(row.get("AdrActCnt")),
                    "TxCnt": _float(row.get("TxCnt")),
                    "FeeTotNtv": _float(row.get("FeeTotNtv")),
                    "source_path": str(path),
                }
            )
    for asset, rows in by_asset.items():
        dedup = {int(row["metric_time_ms"]): row for row in rows}
        by_asset[asset] = [dedup[key] for key in sorted(dedup)]
    return dict(by_asset)


def _return(close_now: float, close_then: float | None) -> float | None:
    if close_then is None or close_then <= 0:
        return None
    return close_now / close_then - 1.0


def _rolling_z(values: list[float | None], idx: int, window: int = 168, min_periods: int = 12) -> float | None:
    current = values[idx]
    if current is None:
        return None
    start = max(0, idx - window + 1)
    history = [x for x in values[start : idx + 1] if x is not None]
    if len(history) < min_periods:
        return None
    mean = statistics.fmean(history)
    stdev = statistics.stdev(history) if len(history) >= 2 else 0.0
    return 0.0 if stdev == 0.0 else (current - mean) / stdev


def _asof(rows: list[dict[str, Any]], timestamp_ms: int, key: str) -> dict[str, Any] | None:
    if not rows:
        return None
    stamps = [int(row[key]) for row in rows]
    pos = bisect_right(stamps, timestamp_ms) - 1
    return rows[pos] if pos >= 0 else None


def _asset_from_spot_symbol(symbol: str) -> str:
    for quote in ("USDT", "USDC", "BUSD", "USD"):
        if symbol.endswith(quote):
            return symbol[: -len(quote)].lower()
    return symbol.lower()


def build_point_in_time_panel(
    spot: dict[str, list[dict[str, Any]]],
    *,
    benchmark_symbol: str = "BTCUSDT",
    derivative_bars: dict[str, list[dict[str, Any]]] | None = None,
    derivative_metrics: dict[str, list[dict[str, Any]]] | None = None,
    derivative_map: dict[str, str] | None = None,
    onchain: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    derivative_bars = derivative_bars or {}
    derivative_metrics = derivative_metrics or {}
    derivative_map = derivative_map or {"BTCUSDT": "BTCUSD_PERP"}
    onchain = onchain or {}

    if benchmark_symbol not in spot:
        raise ValueError(f"benchmark {benchmark_symbol} is absent")

    spot_index: dict[str, dict[int, dict[str, Any]]] = {}
    series: dict[str, dict[str, Any]] = {}
    for symbol, rows in spot.items():
        rows = sorted(rows, key=lambda r: int(r["close_time_ms"]))
        spot_index[symbol] = {int(row["close_time_ms"]): row for row in rows}
        closes = [float(row["close"]) for row in rows]
        timestamps = [int(row["close_time_ms"]) for row in rows]
        ret1 = [None] * len(rows)
        ret4 = [None] * len(rows)
        ret24 = [None] * len(rows)
        order_imb = [None] * len(rows)
        rv24 = [None] * len(rows)
        for i, row in enumerate(rows):
            if i >= 1:
                ret1[i] = _return(closes[i], closes[i - 1])
            if i >= 4:
                ret4[i] = _return(closes[i], closes[i - 4])
            if i >= 24:
                ret24[i] = _return(closes[i], closes[i - 24])
                hourly = [ret1[j] for j in range(i - 23, i + 1) if ret1[j] is not None]
                if len(hourly) >= 12:
                    rv24[i] = statistics.pstdev(hourly) * math.sqrt(24.0)
            volume = float(row["volume"])
            if volume > 0:
                order_imb[i] = 2.0 * float(row["taker_buy_volume"]) / volume - 1.0
        series[symbol] = {
            "rows": rows,
            "timestamps": timestamps,
            "ret1": ret1,
            "ret4": ret4,
            "ret24": ret24,
            "z_ret1": [_rolling_z(ret1, i) for i in range(len(rows))],
            "z_ret4": [_rolling_z(ret4, i) for i in range(len(rows))],
            "z_ret24": [_rolling_z(ret24, i) for i in range(len(rows))],
            "z_order_imb": [_rolling_z(order_imb, i) for i in range(len(rows))],
            "z_rv24": [_rolling_z(rv24, i) for i in range(len(rows))],
        }

    decision_times = sorted(set.intersection(*(set(index) for index in spot_index.values()))) if spot_index else []
    positions = {
        symbol: {ts: i for i, ts in enumerate(data["timestamps"])}
        for symbol, data in series.items()
    }

    basis_by_symbol: dict[str, dict[int, float | None]] = {}
    taker_by_symbol: dict[str, dict[int, float | None]] = {}
    oi_change_by_symbol: dict[str, dict[int, float | None]] = {}

    for spot_symbol, deriv_symbol in derivative_map.items():
        drows = sorted(derivative_bars.get(deriv_symbol, []), key=lambda r: int(r["close_time_ms"]))
        basis: dict[int, float | None] = {}
        for drow in drows:
            ts = int(drow["close_time_ms"])
            srow = spot_index.get(spot_symbol, {}).get(ts)
            if srow and float(srow["close"]) > 0:
                basis[ts] = float(drow["close"]) / float(srow["close"]) - 1.0
        basis_by_symbol[spot_symbol] = basis

        mrows = sorted(derivative_metrics.get(deriv_symbol, []), key=lambda r: int(r["timestamp_ms"]))
        taker: dict[int, float | None] = {}
        oi_change: dict[int, float | None] = {}
        previous_oi: float | None = None
        for ts in decision_times:
            mrow = _asof(mrows, ts, "timestamp_ms")
            if mrow is None:
                continue
            ratio = _float(mrow.get("taker_long_short_ratio"))
            taker[ts] = None if ratio is None or ratio <= 0 else math.tanh(math.log(ratio))
            current_oi = _float(mrow.get("sum_open_interest_value"))
            oi_change[ts] = (
                None
                if current_oi is None or previous_oi in (None, 0.0)
                else current_oi / previous_oi - 1.0
            )
            if current_oi is not None:
                previous_oi = current_oi
        taker_by_symbol[spot_symbol] = taker
        oi_change_by_symbol[spot_symbol] = oi_change

    bench = series[benchmark_symbol]
    bench_index = spot_index[benchmark_symbol]
    output: list[dict[str, Any]] = []
    for ts in decision_times:
        bi = positions[benchmark_symbol].get(ts)
        if bi is None or bi + 1 >= len(bench["rows"]):
            continue
        benchmark_return = _return(
            float(bench["rows"][bi + 1]["close"]),
            float(bench_index[ts]["close"]),
        )
        if benchmark_return is None:
            continue

        current_ret1 = {
            symbol: (None if positions[symbol].get(ts) is None else data["ret1"][positions[symbol][ts]])
            for symbol, data in series.items()
        }

        for symbol, data in sorted(series.items()):
            i = positions[symbol].get(ts)
            if i is None or i + 1 >= len(data["rows"]):
                continue
            row = data["rows"][i]
            next_row = data["rows"][i + 1]
            forward_return = _return(float(next_row["close"]), float(row["close"]))
            peers = [v for peer, v in current_ret1.items() if peer != symbol and v is not None]
            cross = (
                None
                if not peers or data["ret1"][i] is None
                else statistics.fmean(peers) - float(data["ret1"][i])
            )

            asset = _asset_from_spot_symbol(symbol)
            oc_rows = sorted(onchain.get(asset, []), key=lambda r: int(r["available_time_ms"]))
            oc = _asof(oc_rows, ts, "available_time_ms")
            oc_activity = None
            network_growth = None
            if oc:
                adr = _float(oc.get("AdrActCnt"))
                tx = _float(oc.get("TxCnt"))
                fee = _float(oc.get("FeeTotNtv"))
                comps = [math.log1p(v) for v in (adr, tx, fee) if v is not None and v >= 0]
                oc_activity = statistics.fmean(comps) if comps else None
                oc_pos = next((j for j, item in enumerate(oc_rows) if item is oc), None)
                if oc_pos is not None and oc_pos > 0:
                    prev_adr = _float(oc_rows[oc_pos - 1].get("AdrActCnt"))
                    if adr is not None and prev_adr not in (None, 0.0):
                        network_growth = adr / prev_adr - 1.0

            output.append(
                {
                    "timestamp": _iso_from_ms(ts),
                    "decision_time_ms": ts,
                    "asset": symbol,
                    "forward_return": forward_return,
                    "benchmark_return": benchmark_return,
                    "momentum_1h": data["z_ret1"][i],
                    "momentum_4h": data["z_ret4"][i],
                    "momentum_1d": data["z_ret24"][i],
                    "cross_crypto_leadlag": cross,
                    "funding_z": None,
                    "oi_change_z": oi_change_by_symbol.get(symbol, {}).get(ts),
                    "basis_z": basis_by_symbol.get(symbol, {}).get(ts),
                    "taker_imbalance": taker_by_symbol.get(symbol, {}).get(ts),
                    "order_flow_imbalance": data["z_order_imb"][i],
                    "book_imbalance": None,
                    "microprice_edge": None,
                    "onchain_activity_z": oc_activity,
                    "exchange_netflow_z": None,
                    "network_growth_z": network_growth,
                    "sentiment_z": None,
                    "news_novelty": None,
                    "llm_event_score": None,
                    "llm_event_confidence": None,
                    "regime_trend": bench["z_ret24"][bi],
                    "regime_volatility": bench["z_rv24"][bi],
                    "spread_bps": None,
                    "slippage_bps": None,
                    "funding_bps": None,
                    "source_close_time": _iso_from_ms(int(row["close_time_ms"])),
                    "target_close_time": _iso_from_ms(int(next_row["close_time_ms"])),
                }
            )

    # Standardize raw incremental information sets with past-only rolling history.
    # This preserves point-in-time causality and prevents incompatible units from
    # dominating the equal-weight score.
    for feature in (
        "cross_crypto_leadlag",
        "oi_change_z",
        "basis_z",
        "taker_imbalance",
        "onchain_activity_z",
        "network_growth_z",
    ):
        by_asset: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in output:
            by_asset[str(row["asset"])].append(row)
        for rows in by_asset.values():
            rows.sort(key=lambda item: int(item["decision_time_ms"]))
            raw = [_float(item.get(feature)) for item in rows]
            for idx, item in enumerate(rows):
                item[feature] = _rolling_z(raw, idx)

    output.sort(key=lambda item: (int(item["decision_time_ms"]), str(item["asset"])))
    return output


def feature_availability(rows: list[dict[str, Any]], feature_sets: dict[str, list[str]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for model, features in feature_sets.items():
        complete = 0
        ever_present = {feature: False for feature in features}
        for row in rows:
            ok = True
            for feature in features:
                value = _float(row.get(feature))
                if value is not None:
                    ever_present[feature] = True
                else:
                    ok = False
            if ok:
                complete += 1
        result[model] = {
            "rows": len(rows),
            "complete_rows": complete,
            "complete_fraction": 0.0 if not rows else complete / len(rows),
            "missing_features": [f for f, present in ever_present.items() if not present],
        }
    return result


def _parse_iso_utc(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(normalized).astimezone(timezone.utc)


def panel_quality(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_timestamp: dict[str, set[str]] = defaultdict(set)
    seen: set[tuple[str, str]] = set()
    target_after_decision = True
    for row in rows:
        timestamp = str(row["timestamp"])
        asset = str(row["asset"])
        key = (timestamp, asset)
        if key in seen:
            raise ValueError(f"duplicate panel key: {key}")
        seen.add(key)
        by_timestamp[timestamp].add(asset)
        if _parse_iso_utc(str(row["target_close_time"])) <= _parse_iso_utc(timestamp):
            target_after_decision = False

    timestamps = sorted(by_timestamp)
    asset_sets = [by_timestamp[ts] for ts in timestamps]
    stable_universe = not asset_sets or all(s == asset_sets[0] for s in asset_sets)
    max_gap_hours = 0.0
    for left, right in zip(timestamps, timestamps[1:]):
        gap = (_parse_iso_utc(right) - _parse_iso_utc(left)).total_seconds() / 3600.0
        max_gap_hours = max(max_gap_hours, gap)
    continuity_ok = len(timestamps) <= 1 or max_gap_hours <= 1.000001
    return {
        "stable_asset_universe": stable_universe,
        "target_strictly_after_decision": target_after_decision,
        "max_gap_hours": max_gap_hours,
        "hourly_continuity_ok": continuity_ok,
        "duplicate_keys": False,
    }


def readiness_report(rows: list[dict[str, Any]], protocol: dict[str, Any]) -> dict[str, Any]:
    timestamps = sorted({str(row["timestamp"]) for row in rows})
    assets = sorted({str(row["asset"]) for row in rows})
    wf = protocol["walk_forward"]
    minimum = int(wf["min_train_rows"]) + int(wf["purge_rows"]) + int(wf["test_rows"])
    quality = panel_quality(rows)
    history_ready = len(timestamps) >= minimum and all(
        (
            quality["stable_asset_universe"],
            quality["target_strictly_after_decision"],
            quality["hourly_continuity_ok"],
            not quality["duplicate_keys"],
        )
    )
    return {
        "schema_version": "1.1.0",
        "mode": "RESEARCH_ONLY",
        "decision_timestamps": len(timestamps),
        "assets": assets,
        "asset_count": len(assets),
        "minimum_timestamps_for_first_fold": minimum,
        "history_ready_for_first_fold": history_ready,
        "data_quality": quality,
        "feature_availability": feature_availability(rows, protocol["feature_sets"]),
        "holdout_accessed": False,
        "EDGE_VERIFIED": False,
        "paper_authorized": False,
        "testnet_authorized": False,
        "live_authorized": False,
        "decision": "DATASET_READY_FOR_ABLATION" if history_ready else "ACCUMULATE_MORE_PROSPECTIVE_DATA",
    }


def write_panel_csv(rows: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        output.write_text("", encoding="utf-8")
        return
    columns = list(rows[0].keys())
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if value is None else value for key, value in row.items()})
