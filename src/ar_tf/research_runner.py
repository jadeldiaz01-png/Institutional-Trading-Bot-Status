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


def build_daily_targets(frames: dict[str, pd.DataFrame], cfg: ResearchConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    features = {symbol: build_features(frame, cfg) for symbol, frame in frames.items()}
    common = sorted(set().union(*(set(x.index) for x in features.values())))
    idx = pd.DatetimeIndex(common)
    returns = pd.DataFrame(index=idx, columns=sorted(features), dtype=float)
    weights = pd.DataFrame(0.0, index=idx, columns=sorted(features), dtype=float)
    for symbol, x in features.items():
        returns[symbol] = x["close"].pct_change().reindex(idx)
    for ts in idx:
        sig = pd.Series({s: build_signal(x, cfg).get(ts, np.nan) for s, x in features.items()}, dtype=float)
        vol = pd.Series({s: x["ann_vol"].get(ts, np.nan) for s, x in features.items()}, dtype=float)
        w = portfolio_weights(sig, vol, cfg)
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
    if not dataset_manifest.get("point_in_time") or not dataset_manifest.get("sha256"):
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
    )
    returns, weights = build_daily_targets(frames, cfg)
    research_idx, holdout_idx = freeze_holdout(returns.index, holdout_days)
    # Parameter selection must use research_idx only. Holdout is evaluated once after selection.
    costs = CostModel(
        taker_fee_bps=config["costs"]["taker_fee_bps"],
        half_spread_bps=config["costs"]["half_spread_bps"],
        slippage_bps=config["costs"]["base_slippage_bps"],
    )
    registry = JsonlExperimentRegistry(registry_path)
    oos_parts = []
    trial_metrics = []
    splits = list(walk_forward_splits(
        research_idx,
        train_days=validation["train_days"], test_days=validation["test_days"],
        step_days=validation["step_days"], embargo_days=validation["embargo_days"],
    ))
    if not splits:
        return {"decision": "NO_GO", "reasons": ["INSUFFICIENT_WALK_FORWARD_HISTORY"], "paper_authorized": False}
    params = {"strategy": config["strategy_id"], "features": config["features"], "portfolio": config["portfolio"]}
    for i, (_, test_idx) in enumerate(splits):
        bt = run_backtest(returns.loc[test_idx], weights.loc[test_idx], costs)
        metrics = performance_metrics(bt["net_return"])
        registry.append(make_record(dataset_manifest["sha256"], code_ref, params, {"fold": i, "kind": "walk_forward_oos"}, metrics, "COMPLETE"))
        oos_parts.append(bt["net_return"])
        trial_metrics.append(metrics)
    oos = pd.concat(oos_parts).sort_index()
    oos = oos[~oos.index.duplicated(keep="first")]
    metrics = performance_metrics(oos)
    skew = float(oos.skew()) if len(oos) > 2 else 0.0
    kurt = float(oos.kurtosis() + 3) if len(oos) > 3 else 3.0
    dsr = deflated_sharpe_probability(metrics["sharpe"], len(oos), skew, kurt, trials=max(1, len(splits)))
    # Full PBO requires a matrix of competing parameter trials. Until that grid exists, fail closed.
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
        "dataset_sha256": dataset_manifest["sha256"],
        "code_ref": code_ref,
        "holdout_frozen": {"start": holdout_idx.min().isoformat(), "end": holdout_idx.max().isoformat(), "evaluated": False},
        "walk_forward_folds": len(splits),
        "oos_metrics": metrics,
        "dsr_probability": dsr,
        "pbo": None,
        "bootstrap_sharpe_p05": float(np.nanquantile(bootstrap, 0.05)) if bootstrap.size else None,
        "monte_carlo_drawdown_p05": float(np.nanquantile(mc_dd, 0.05)) if mc_dd.size else None,
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
