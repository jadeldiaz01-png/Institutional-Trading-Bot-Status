from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from .backtest import CostModel, run_backtest, walk_forward_splits
from .core import ResearchConfig, build_features, build_signal, portfolio_weights
from .experiments import JsonlExperimentRegistry, make_record
from .validation import (
    bootstrap_sharpe,
    certification_decision,
    deflated_sharpe_probability,
    monte_carlo_drawdowns,
    performance_metrics,
)


def load_market_dir(path: str | Path) -> dict[str, pd.DataFrame]:
    frames = {}
    for file in sorted(Path(path).glob("*.csv")):
        frame = pd.read_csv(file, parse_dates=["timestamp"]).set_index("timestamp").sort_index()
        if frame.index.tz is None:
            frame.index = frame.index.tz_localize("UTC")
        else:
            frame.index = frame.index.tz_convert("UTC")
        frames[file.stem.upper()] = frame
    if not frames:
        raise ValueError("NO_GO: no historical market files supplied")
    return frames


def _raw_symbol(market_id: str, frame: pd.DataFrame) -> str:
    if "symbol" in frame.columns and not frame["symbol"].dropna().empty:
        return str(frame["symbol"].dropna().iloc[0]).upper()
    return market_id.split("__E", 1)[0].upper()


def build_daily_targets(
    frames: dict[str, pd.DataFrame],
    cfg: ResearchConfig,
    universe_cfg: dict | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build causal daily targets over a point-in-time liquidity universe."""
    universe_cfg = universe_cfg or {}
    max_assets = int(universe_cfg.get("max_assets", max(1, len(frames))))
    min_history_days = int(universe_cfg.get("min_history_days", 0))
    min_notional = float(universe_cfg.get("min_median_daily_notional_usd", 0.0))
    liquidity_lookback = int(universe_cfg.get("liquidity_lookback_days", 30))
    exclude_patterns = tuple(str(x).upper() for x in universe_cfg.get("exclude_patterns", []))
    exclude_base_assets = {str(x).upper() for x in universe_cfg.get("exclude_base_assets", [])}
    if max_assets < 1 or liquidity_lookback < 1:
        raise ValueError("NO_GO: invalid point-in-time universe configuration")

    features = {market_id: build_features(frame, cfg) for market_id, frame in frames.items()}
    common = sorted(set().union(*(set(x.index) for x in features.values())))
    idx = pd.DatetimeIndex(common)
    columns = sorted(features)
    returns = pd.DataFrame(index=idx, columns=columns, dtype=float)
    signals = pd.DataFrame(index=idx, columns=columns, dtype=float)
    vols = pd.DataFrame(index=idx, columns=columns, dtype=float)
    notionals = pd.DataFrame(index=idx, columns=columns, dtype=float)
    history = pd.DataFrame(0, index=idx, columns=columns, dtype=int)
    raw_symbols: dict[str, str] = {}

    for market_id, x in features.items():
        raw = _raw_symbol(market_id, frames[market_id])
        raw_symbols[market_id] = raw
        returns[market_id] = x["close"].pct_change().reindex(idx)
        signals[market_id] = build_signal(x, cfg).reindex(idx)
        vols[market_id] = x["ann_vol"].reindex(idx)
        notionals[market_id] = x["notional"].reindex(idx)
        history[market_id] = x["close"].notna().astype(int).cumsum().reindex(idx).ffill().fillna(0).astype(int)

    liquidity = notionals.rolling(
        liquidity_lookback,
        min_periods=max(2, min(liquidity_lookback, liquidity_lookback // 3 or 1)),
    ).median()
    weights = pd.DataFrame(0.0, index=idx, columns=columns, dtype=float)

    static_allowed: dict[str, bool] = {}
    for market_id, raw in raw_symbols.items():
        base = raw[:-4] if raw.endswith("USDT") else raw
        pattern_excluded = any(raw.endswith(pattern) for pattern in exclude_patterns)
        static_allowed[market_id] = raw.endswith("USDT") and not pattern_excluded and base not in exclude_base_assets

    for ts in idx:
        liq = liquidity.loc[ts]
        current_notional = notionals.loc[ts]
        hist = history.loc[ts]
        mask = pd.Series({
            market_id: bool(
                static_allowed[market_id]
                and hist.get(market_id, 0) >= min_history_days
                and np.isfinite(current_notional.get(market_id, np.nan))
                and np.isfinite(liq.get(market_id, np.nan))
                and liq.get(market_id, 0.0) >= min_notional
            )
            for market_id in columns
        })
        eligible_liq = liq[mask].dropna().sort_values(ascending=False)
        selected = list(eligible_liq.head(max_assets).index)
        if not selected:
            continue
        sig = signals.loc[ts, selected].dropna()
        vol = vols.loc[ts, selected].dropna()
        common_selected = sig.index.intersection(vol.index)
        if common_selected.empty:
            continue
        w = portfolio_weights(sig.loc[common_selected], vol.loc[common_selected], cfg)
        if not w.empty:
            weights.loc[ts, w.index] = w
    return returns, weights


def freeze_holdout(index: pd.DatetimeIndex, holdout_days: int) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    if holdout_days <= 0:
        raise ValueError("holdout_days must be positive")
    cutoff = index.max() - pd.Timedelta(days=holdout_days)
    research = index[index < cutoff]
    holdout = index[index >= cutoff]
    if research.empty or holdout.empty:
        raise ValueError("NO_GO: insufficient history to freeze holdout")
    return research, holdout


def run_research(frames: dict[str, pd.DataFrame], dataset_manifest: dict, code_ref: str, config: dict, registry_path: str | Path) -> dict:
    dataset_sha = dataset_manifest.get("dataset_sha256") or dataset_manifest.get("sha256")
    if not dataset_manifest.get("point_in_time") or not dataset_sha:
        return {"decision": "NO_GO", "reasons": ["INVALID_DATASET_MANIFEST"], "paper_authorized": False}
    validation = config["validation"]
    holdout_days = int(validation.get("holdout_days", 365))
    cfg = ResearchConfig(
        momentum_days=tuple(config["features"]["momentum_days"]),
        ema_fast_days=config["features"]["ema_fast_days"],
        ema_slow_days=config["features"]["ema_slow_days"],
        donchian_days=config["features"]["donchian_days"],
        vol_days=config["features"]["vol_days"],
        target_annual_vol=config["portfolio"]["target_annual_vol"],
        max_asset_weight=config["portfolio"]["max_asset_weight"],
        max_gross_exposure=config["portfolio"]["max_gross_exposure"],
        trend_threshold=config.get("regime", {}).get("trend_threshold", 0.25),
        stress_vol_z=config.get("regime", {}).get("stress_vol_z", 2.0),
    )
    returns, weights = build_daily_targets(frames, cfg, config.get("universe", {}))
    research_idx, holdout_idx = freeze_holdout(returns.index, holdout_days)
    costs = CostModel(
        taker_fee_bps=config["costs"]["taker_fee_bps"],
        half_spread_bps=config["costs"]["half_spread_bps"],
        slippage_bps=config["costs"]["base_slippage_bps"],
    )
    registry = JsonlExperimentRegistry(registry_path)
    oos_parts = []
    splits = list(walk_forward_splits(
        research_idx,
        train_days=validation["train_days"], test_days=validation["test_days"],
        step_days=validation["step_days"], embargo_days=validation["embargo_days"],
    ))
    if not splits:
        return {"decision": "NO_GO", "reasons": ["INSUFFICIENT_WALK_FORWARD_HISTORY"], "paper_authorized": False}
    params = {"strategy": config["strategy_id"], "universe": config.get("universe", {}), "features": config["features"], "portfolio": config["portfolio"]}
    for i, (_, test_idx) in enumerate(splits):
        bt = run_backtest(returns.loc[test_idx], weights.loc[test_idx], costs)
        metrics = performance_metrics(bt["net_return"])
        registry.append(make_record(dataset_sha, code_ref, params, {"fold": i, "kind": "walk_forward_oos"}, metrics, "COMPLETE"))
        oos_parts.append(bt["net_return"])
    oos = pd.concat(oos_parts).sort_index()
    oos = oos[~oos.index.duplicated(keep="first")]
    metrics = performance_metrics(oos)
    skew = float(oos.skew()) if len(oos) > 2 else 0.0
    kurt = float(oos.kurtosis() + 3) if len(oos) > 3 else 3.0
    # Folds are not independent strategy trials. Multiplicity is handled only in
    # the actual tournament; this single-strategy precheck uses a zero benchmark.
    dsr = deflated_sharpe_probability(metrics["sharpe"], len(oos), skew, kurt, benchmark_sharpe=0.0)
    pbo = float("nan")
    stress = []
    for multiplier in config["costs"]["adverse_multipliers"]:
        stress_bt = run_backtest(returns.loc[research_idx], weights.loc[research_idx], costs, float(multiplier))
        stress.append(performance_metrics(stress_bt["net_return"]))
    decision = certification_decision(metrics, dsr, pbo, stress, min_trades=validation["min_trades"], max_pbo=validation["max_pbo"], min_dsr=validation["min_deflated_sharpe_probability"])
    bootstrap = bootstrap_sharpe(oos, samples=validation["bootstrap_samples"])
    mc_dd = monte_carlo_drawdowns(oos, paths=validation["monte_carlo_paths"])
    report = {
        **decision,
        "paper_authorized": False,
        "dataset_sha256": dataset_sha,
        "code_ref": code_ref,
        "holdout_frozen": {"start": holdout_idx.min().isoformat(), "end": holdout_idx.max().isoformat(), "evaluated": False},
        "walk_forward_folds": len(splits),
        "oos_metrics": metrics,
        "dsr_probability": dsr,
        "pbo": None,
        "bootstrap_sharpe_p05": float(np.nanquantile(bootstrap, 0.05)) if bootstrap.size else None,
        "block_bootstrap_drawdown_p05": float(np.nanquantile(mc_dd, 0.05)) if mc_dd.size else None,
        "stress_metrics": stress,
        "required_next_gate": "PARAMETER_GRID_PBO_THEN_SINGLE_UNTOUCHED_HOLDOUT",
    }
    return report


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--market-dir", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--config", default="config/ar_tf_v1.yaml")
    p.add_argument("--registry", default="artifacts/experiments/ar_tf_v1.jsonl")
    p.add_argument("--output", default="artifacts/ar-tf-v1b-research-report.json")
    p.add_argument("--code-ref", default="UNSPECIFIED")
    args = p.parse_args()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    report = run_research(load_market_dir(args.market_dir), manifest, args.code_ref, config, args.registry)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
