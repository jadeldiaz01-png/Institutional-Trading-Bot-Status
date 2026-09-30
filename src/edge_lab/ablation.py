"""Deterministic research-only M0→M7 ablation evaluator.

Supports a point-in-time asset panel. At each timestamp, positions are equally
weighted across the configured asset universe (inactive assets remain cash).
The existing CP03 holdout is never opened and this module never grants execution
authority.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class CostModel:
    taker_fee_bps: float = 4.0
    maker_fee_bps: float = 2.0
    default_half_spread_bps: float = 1.0
    default_slippage_bps: float = 2.0
    execution_style: str = "taker"

    def fee_bps(self) -> float:
        if self.execution_style == "maker":
            return self.maker_fee_bps
        if self.execution_style == "taker":
            return self.taker_fee_bps
        raise ValueError(f"unsupported execution_style: {self.execution_style}")

    def execution_cost_fraction(self, turnover: float, row: dict[str, Any]) -> float:
        spread = _finite_float(row.get("spread_bps"))
        half_spread = self.default_half_spread_bps if spread is None else max(0.0, spread) / 2.0
        slippage = _finite_float(row.get("slippage_bps"))
        slippage_bps = self.default_slippage_bps if slippage is None else max(0.0, slippage)
        one_way_bps = self.fee_bps() + half_spread + slippage_bps
        return max(0.0, turnover) * one_way_bps / 10_000.0


def _finite_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def make_walk_forward_folds(
    n_rows: int,
    *,
    min_train_rows: int,
    test_rows: int,
    step_rows: int,
    purge_rows: int,
    embargo_rows: int,
) -> list[dict[str, int]]:
    if min(n_rows, min_train_rows, test_rows, step_rows) < 1:
        raise ValueError("row counts must be positive")
    if purge_rows < 0 or embargo_rows < 0:
        raise ValueError("purge/embargo must be non-negative")

    folds: list[dict[str, int]] = []
    train_end = min_train_rows
    fold_id = 0
    while True:
        test_start = train_end + purge_rows
        if test_start >= n_rows:
            break
        test_end = min(test_start + test_rows, n_rows)
        if test_end <= test_start:
            break
        folds.append({
            "fold": fold_id,
            "train_start": 0,
            "train_end_exclusive": train_end,
            "purge_start": train_end,
            "test_start": test_start,
            "test_end_exclusive": test_end,
            "embargo_end_exclusive": min(n_rows, test_end + embargo_rows),
        })
        fold_id += 1
        train_end += step_rows
    return folds


def _feature_value(row: dict[str, Any], feature: str) -> float | None:
    value = _finite_float(row.get(feature))
    if value is None:
        return None
    if feature == "llm_event_confidence":
        return None
    if feature == "llm_event_score":
        confidence = _finite_float(row.get("llm_event_confidence"))
        if confidence is not None:
            value *= min(1.0, max(0.0, confidence))
    return value


def score_row(row: dict[str, Any], features: Iterable[str], *, clip_abs_z: float) -> float:
    usable: list[float] = []
    for feature in features:
        value = _feature_value(row, feature)
        if value is None:
            continue
        clipped = max(-clip_abs_z, min(clip_abs_z, value))
        usable.append(clipped / clip_abs_z)
    if not usable:
        return 0.0
    return max(-1.0, min(1.0, statistics.fmean(usable)))


def position_from_score(score: float, *, entry_threshold: float) -> int:
    if score >= entry_threshold:
        return 1
    if score <= -entry_threshold:
        return -1
    return 0


def _group_panel(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    groups: dict[str, list[dict[str, Any]]] = {}
    seen_pairs: set[tuple[str, str]] = set()
    for row in rows:
        timestamp = str(row.get("timestamp", ""))
        if not timestamp:
            raise ValueError("every row requires timestamp")
        asset = str(row.get("asset") or "__portfolio__")
        pair = (timestamp, asset)
        if pair in seen_pairs:
            raise ValueError(f"duplicate timestamp/asset pair: {pair}")
        seen_pairs.add(pair)
        groups.setdefault(timestamp, []).append(row)

    timestamps = sorted(groups)
    first_assets: set[str] | None = None
    result: list[dict[str, Any]] = []
    for timestamp in timestamps:
        group_rows = groups[timestamp]
        asset_rows: dict[str, dict[str, Any]] = {}
        benchmark_values: list[float] = []
        for row in group_rows:
            asset = str(row.get("asset") or "__portfolio__")
            asset_rows[asset] = row
            benchmark = _finite_float(row.get("benchmark_return"))
            if benchmark is None:
                raise ValueError(f"{timestamp}/{asset} lacks finite benchmark_return")
            benchmark_values.append(benchmark)

        assets = set(asset_rows)
        if first_assets is None:
            first_assets = assets
        elif assets != first_assets:
            missing = sorted(first_assets - assets)
            extra = sorted(assets - first_assets)
            raise ValueError(f"asset universe changed at {timestamp}; missing={missing}, extra={extra}")

        if max(benchmark_values) - min(benchmark_values) > 1e-12:
            raise ValueError(f"inconsistent benchmark_return within timestamp {timestamp}")

        result.append({
            "timestamp": timestamp,
            "asset_rows": asset_rows,
            "benchmark_return": benchmark_values[0],
        })
    return result


def _missing_required_features(
    groups: list[dict[str, Any]],
    folds: list[dict[str, int]],
    features: list[str],
) -> dict[str, int]:
    missing = {feature: 0 for feature in features}
    for fold in folds:
        for idx in range(fold["test_start"], fold["test_end_exclusive"]):
            for row in groups[idx]["asset_rows"].values():
                for feature in features:
                    if _finite_float(row.get(feature)) is None:
                        missing[feature] += 1
    return {feature: count for feature, count in missing.items() if count > 0}


def _run_test_groups(
    groups: list[dict[str, Any]],
    indices: Iterable[int],
    *,
    features: list[str],
    cost_model: CostModel,
    entry_threshold: float,
    clip_abs_z: float,
) -> dict[str, Any]:
    previous_positions: dict[str, int] = {}
    net_returns: list[float] = []
    gross_returns: list[float] = []
    benchmark_returns: list[float] = []
    total_execution_cost = 0.0
    total_funding_pnl = 0.0
    turnover_total = 0.0
    transitions = 0

    for idx in indices:
        group = groups[idx]
        asset_rows: dict[str, dict[str, Any]] = group["asset_rows"]
        universe_size = len(asset_rows)
        if universe_size < 1:
            raise ValueError(f"group {idx} has empty asset universe")

        gross_sum = cost_sum = funding_sum = turnover_sum = 0.0
        next_positions: dict[str, int] = {}
        for asset, row in sorted(asset_rows.items()):
            forward_return = _finite_float(row.get("forward_return"))
            if forward_return is None:
                raise ValueError(f"group {idx}/{asset} lacks finite forward_return")

            score = score_row(row, features, clip_abs_z=clip_abs_z)
            position = position_from_score(score, entry_threshold=entry_threshold)
            previous = previous_positions.get(asset, 0)
            turnover = abs(position - previous)
            if turnover > 0:
                transitions += 1

            gross_sum += position * forward_return
            cost_sum += cost_model.execution_cost_fraction(turnover, row)
            funding_bps = _finite_float(row.get("funding_bps")) or 0.0
            funding_sum += -position * funding_bps / 10_000.0
            turnover_sum += turnover
            next_positions[asset] = position

        gross = gross_sum / universe_size
        execution_cost = cost_sum / universe_size
        funding_pnl = funding_sum / universe_size
        turnover = turnover_sum / universe_size
        net = gross - execution_cost + funding_pnl
        if net <= -1.0:
            raise ValueError(f"group {idx} produces net return <= -100%; invalid for compounding")

        gross_returns.append(gross)
        net_returns.append(net)
        benchmark_returns.append(float(group["benchmark_return"]))
        total_execution_cost += execution_cost
        total_funding_pnl += funding_pnl
        turnover_total += turnover
        previous_positions = next_positions

    return {
        "net_returns": net_returns,
        "gross_returns": gross_returns,
        "benchmark_returns": benchmark_returns,
        "execution_cost": total_execution_cost,
        "funding_pnl": total_funding_pnl,
        "turnover": turnover_total,
        "transitions": transitions,
    }


def _compound(returns: Iterable[float]) -> float:
    equity = 1.0
    for value in returns:
        equity *= 1.0 + value
    return equity - 1.0


def _max_drawdown(returns: Iterable[float]) -> float:
    equity = 1.0
    peak = 1.0
    worst = 0.0
    for value in returns:
        equity *= 1.0 + value
        peak = max(peak, equity)
        worst = min(worst, equity / peak - 1.0)
    return worst


def _sharpe(returns: list[float], annualization_periods: int) -> float | None:
    if len(returns) < 2:
        return None
    stdev = statistics.stdev(returns)
    if stdev == 0.0:
        return None
    return statistics.fmean(returns) / stdev * math.sqrt(annualization_periods)


def _summarize(parts: list[dict[str, Any]], *, annualization_periods: int) -> dict[str, Any]:
    net: list[float] = []
    gross: list[float] = []
    bench: list[float] = []
    execution_cost = funding_pnl = turnover = 0.0
    transitions = 0
    for part in parts:
        net.extend(part["net_returns"])
        gross.extend(part["gross_returns"])
        bench.extend(part["benchmark_returns"])
        execution_cost += part["execution_cost"]
        funding_pnl += part["funding_pnl"]
        turnover += part["turnover"]
        transitions += part["transitions"]

    net_total = _compound(net)
    benchmark_total = _compound(bench)
    return {
        "observations": len(net),
        "gross_return": _compound(gross),
        "net_return": net_total,
        "benchmark_return": benchmark_total,
        "simple_alpha": net_total - benchmark_total,
        "sharpe": _sharpe(net, annualization_periods),
        "max_drawdown": _max_drawdown(net),
        "turnover": turnover,
        "position_transitions": transitions,
        "trade_transitions": transitions,
        "execution_cost_fraction_sum": execution_cost,
        "funding_pnl_fraction_sum": funding_pnl,
    }


def evaluate_models(rows: list[dict[str, Any]], protocol: dict[str, Any]) -> dict[str, Any]:
    authority = protocol.get("authority", {})
    if authority.get("edge_verified") is not False:
        raise ValueError("protocol must keep edge_verified=false")
    if authority.get("holdout_access") != "FORBIDDEN":
        raise ValueError("protocol must forbid holdout access")
    for key in ("paper_authorized", "testnet_authorized", "live_authorized"):
        if authority.get(key) is not False:
            raise ValueError(f"protocol must keep {key}=false")

    groups = _group_panel(rows)
    if not groups:
        raise ValueError("dataset is empty")

    wf = protocol["walk_forward"]
    folds = make_walk_forward_folds(
        len(groups),
        min_train_rows=int(wf["min_train_rows"]),
        test_rows=int(wf["test_rows"]),
        step_rows=int(wf["step_rows"]),
        purge_rows=int(wf["purge_rows"]),
        embargo_rows=int(wf["embargo_rows"]),
    )
    if not folds:
        raise ValueError("dataset is too short for configured walk-forward")

    signal = protocol["signal"]
    entry_threshold = float(signal["entry_threshold"])
    clip_abs_z = float(signal["feature_clip_abs_z"])
    if not 0.0 < entry_threshold <= 1.0 or clip_abs_z <= 0.0:
        raise ValueError("invalid signal configuration")

    c = protocol["cost_model"]
    cost_model = CostModel(
        taker_fee_bps=float(c["taker_fee_bps"]),
        maker_fee_bps=float(c["maker_fee_bps"]),
        default_half_spread_bps=float(c["default_half_spread_bps"]),
        default_slippage_bps=float(c["default_slippage_bps"]),
        execution_style=str(c["execution_style"]),
    )
    annualization = int(protocol["annualization_periods"])
    screen = protocol["candidate_screen"]

    models: dict[str, Any] = {}
    eligible_models: list[str] = []
    blocked_models: list[str] = []
    for model_name in sorted(protocol["feature_sets"]):
        features = list(protocol["feature_sets"][model_name])
        missing_required = _missing_required_features(groups, folds, features)
        if missing_required:
            blocked_models.append(model_name)
            models[model_name] = {
                "features": features,
                "status": "BLOCKED_MISSING_FEATURES",
                "missing_features": sorted(missing_required),
                "missing_observations_by_feature": missing_required,
                "candidate_screen_pass": False,
                "overall": None,
                "folds": [],
            }
            continue

        eligible_models.append(model_name)
        fold_parts: list[dict[str, Any]] = []
        fold_summaries: list[dict[str, Any]] = []
        positive_folds = 0

        for fold in folds:
            part = _run_test_groups(
                groups,
                range(fold["test_start"], fold["test_end_exclusive"]),
                features=features,
                cost_model=cost_model,
                entry_threshold=entry_threshold,
                clip_abs_z=clip_abs_z,
            )
            fold_parts.append(part)
            summary = _summarize([part], annualization_periods=annualization)
            summary["fold"] = fold["fold"]
            summary["test_start"] = fold["test_start"]
            summary["test_end_exclusive"] = fold["test_end_exclusive"]
            summary["test_start_timestamp"] = groups[fold["test_start"]]["timestamp"]
            summary["test_end_timestamp"] = groups[fold["test_end_exclusive"] - 1]["timestamp"]
            if summary["net_return"] > 0.0:
                positive_folds += 1
            fold_summaries.append(summary)

        overall = _summarize(fold_parts, annualization_periods=annualization)
        positive_fraction = positive_folds / len(folds)
        overall["positive_folds"] = positive_folds
        overall["fold_count"] = len(folds)
        overall["positive_fold_fraction"] = positive_fraction
        sharpe = overall["sharpe"]
        candidate = (
            (not screen.get("require_net_return_positive") or overall["net_return"] > 0.0)
            and (not screen.get("require_simple_alpha_positive") or overall["simple_alpha"] > 0.0)
            and positive_fraction >= float(screen["require_positive_fold_fraction"])
            and (not screen.get("require_sharpe_positive") or (sharpe is not None and sharpe > 0.0))
        )
        models[model_name] = {
            "features": features,
            "status": "EVALUATED_OOS",
            "missing_features": [],
            "candidate_screen_pass": bool(candidate),
            "overall": overall,
            "folds": fold_summaries,
        }

    assets = sorted(groups[0]["asset_rows"])
    return {
        "schema_version": "2.0.0",
        "experiment_id": protocol["experiment_id"],
        "mode": "RESEARCH_ONLY",
        "panel": {
            "decision_timestamps": len(groups),
            "assets": assets,
            "asset_count": len(assets),
            "portfolio_weighting": "equal_weight_across_configured_universe_cash_when_inactive",
        },
        "holdout_accessed": False,
        "paper_authorized": False,
        "testnet_authorized": False,
        "live_authorized": False,
        "EDGE_VERIFIED": False,
        "decision": "NO_EDGE_VERIFIED",
        "walk_forward_folds": folds,
        "eligible_models": eligible_models,
        "blocked_models": blocked_models,
        "models": models,
    }
