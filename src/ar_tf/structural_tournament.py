from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from .advanced_validation import BootstrapConfig, paired_block_bootstrap_superiority, regime_stability_test, white_reality_check
from .backtest import CostModel, run_backtest
from .research_panel import ResearchPanel, rolling_liquidity_universe
from .robustness import capacity_gate, parameter_grid_plateau, perturbation_suite, regime_decomposition
from .spa_validation import SPAConfig, hansen_spa
from .structural_trials import build_structural_weights
from .validation import deflated_sharpe_probability, expected_max_sharpe, performance_metrics, probability_of_backtest_overfitting

STRUCTURAL_FAMILIES = {
    "time_series_momentum", "donchian_breakout", "cross_sectional_momentum",
    "lagged_dispersion_momentum", "price_path_continuity", "volatility_conditioned_reversal",
}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _common_oos_index(panel: ResearchPanel, folds_path: str | Path) -> pd.DatetimeIndex:
    cfg=yaml.safe_load(Path(folds_path).read_text(encoding="utf-8"))
    idx=pd.DatetimeIndex([],tz="UTC")
    for fold in cfg["walk_forward"]["folds"]:
        start=pd.Timestamp(fold["test_start"],tz="UTC"); end=pd.Timestamp(fold["test_end"],tz="UTC")
        idx=idx.union(panel.close.index[(panel.close.index>=start)&(panel.close.index<=end)])
    if idx.empty: raise ValueError("no OOS folds")
    return idx.sort_values()


def _run_weights(panel: ResearchPanel, weights: pd.DataFrame, multiplier: float) -> pd.Series:
    return run_backtest(panel.returns,weights,costs=CostModel(),cost_multiplier=multiplier,missing_held_asset_return=-0.25)["net_return"]


def _btc_benchmark(panel: ResearchPanel) -> pd.Series:
    cols=[c for c in panel.close.columns if c.startswith("BTCUSDT__")]
    if not cols: raise ValueError("BTC benchmark unavailable")
    return panel.returns[cols[0]].fillna(0.0)


def _equal_weight_benchmark(panel: ResearchPanel) -> pd.Series:
    u=rolling_liquidity_universe(panel,max_assets=15)
    w=u.astype(float).div(u.sum(axis=1).replace(0,np.nan),axis=0).fillna(0.0)
    return _run_weights(panel,w,1.0)


def _simple_long_cash_trend_benchmark(panel: ResearchPanel) -> pd.Series:
    cols=[c for c in panel.close.columns if c.startswith("BTCUSDT__")]
    if not cols: raise ValueError("BTC benchmark unavailable")
    c=panel.close[cols[0]]
    fast=c.shift(1).rolling(50,min_periods=50).mean()
    slow=c.shift(1).rolling(200,min_periods=200).mean()
    w=pd.DataFrame(0.0,index=panel.close.index,columns=panel.close.columns)
    w.loc[:,cols[0]]=(fast>slow).astype(float)
    return _run_weights(panel,w,1.0)


def _benchmark_suite(panel: ResearchPanel, oos: pd.DatetimeIndex) -> dict[str,pd.Series]:
    return {
        "btc_buy_and_hold":_btc_benchmark(panel).reindex(oos).fillna(0.0),
        "equal_weight_point_in_time_universe":_equal_weight_benchmark(panel).reindex(oos).fillna(0.0),
        "simple_long_cash_trend":_simple_long_cash_trend_benchmark(panel).reindex(oos).fillna(0.0),
    }


def _market_regime(panel: ResearchPanel) -> pd.Series:
    btc=_btc_benchmark(panel); price=(1.0+btc.fillna(0.0)).cumprod(); slow=price.ewm(span=200,adjust=False).mean()
    vol=btc.rolling(30,min_periods=20).std()*np.sqrt(365.0)
    vol_z=(vol-vol.rolling(365,min_periods=90).mean())/vol.rolling(365,min_periods=90).std(ddof=0).replace(0,np.nan)
    r=pd.Series("SIDEWAYS",index=btc.index,dtype="object"); r.loc[price>slow*1.03]="BULL"; r.loc[price<slow*0.97]="BEAR"; r.loc[vol_z>1.5]="HIGH_VOL"
    return r.shift(1)


def _capacity_evidence(panel: ResearchPanel, weights: pd.DataFrame, oos: pd.DatetimeIndex) -> dict[str, Any]:
    w=weights.reindex(oos).fillna(0.0); delta=w.diff().abs().fillna(w.abs())
    qv=panel.quote_volume.shift(1).rolling(30,min_periods=10).median().reindex(oos); participation=0.01
    daily_capacity=(qv*participation).div(delta.replace(0,np.nan)).min(axis=1,skipna=True).replace([np.inf,-np.inf],np.nan).dropna()
    turnover=delta.sum(axis=1)
    return {"method":"1_PERCENT_LAGGED_MEDIAN_QUOTE_VOLUME_PROXY","participation_rate":participation,
        "median_one_way_turnover":float(turnover.median()),"p95_one_way_turnover":float(turnover.quantile(0.95)),
        "median_capacity_usd":float(daily_capacity.median()) if not daily_capacity.empty else None,
        "p05_capacity_usd":float(daily_capacity.quantile(0.05)) if not daily_capacity.empty else None,
        "positive_capacity":bool(not daily_capacity.empty and daily_capacity.quantile(0.05)>0),"scaled_live_requires_recertification":True}


def _portfolio_evidence(panel: ResearchPanel, weights: pd.DataFrame, oos: pd.DatetimeIndex) -> dict[str, Any]:
    w=weights.reindex(oos).fillna(0.0); executed=w.shift(1).fillna(0.0)
    gross=executed.sum(axis=1); max_w=executed.max(axis=1); hhi=(executed.pow(2).sum(axis=1))
    contributions=(executed*panel.returns.reindex(oos).fillna(0.0))
    net=_run_weights(panel,weights,1.0).reindex(oos).fillna(0.0)
    ann_vol=float(net.std(ddof=1)*np.sqrt(365.0)) if len(net)>1 else None
    var95=float(net.quantile(0.05)); tail=net[net<=var95]; cvar95=float(tail.mean()) if not tail.empty else var95
    total_contrib=contributions.sum(axis=0); denom=float(total_contrib.abs().sum())
    max_abs_contrib_share=float(total_contrib.abs().max()/denom) if denom>0 else 0.0
    return {"max_observed_gross":float(gross.max()),"max_observed_asset_weight":float(max_w.max()),
        "max_hhi":float(hhi.max()),"median_effective_positions":float((1.0/hhi.replace(0,np.nan)).median()),
        "annualized_realized_volatility":ann_vol,"var_95":var95,"cvar_95":cvar95,
        "max_absolute_asset_contribution_share":max_abs_contrib_share,
        "gross_limit_respected":bool((gross<=1.000001).all()),"asset_limit_respected":bool((max_w<=0.150001).all()),
        "long_cash_only":bool((executed>=-1e-12).all(axis=None)),"contribution_concentration_reasonable":bool(max_abs_contrib_share<=0.60)}


def run_structural_tournament(panel: ResearchPanel, registry: dict[str, Any], folds_path: str | Path) -> dict[str, Any]:
    oos=_common_oos_index(panel,folds_path); trials=[t for t in registry["trials"] if t["family"] in STRUCTURAL_FAMILIES]
    if len(trials)!=122: raise ValueError(f"expected 122 structural trials, got {len(trials)}")
    base={}; stressed={}; severe={}; weights_by_trial={}; failures=[]
    for trial in trials:
        tid=trial["trial_id"]
        try:
            w=build_structural_weights(panel,trial["family"],trial["params"]); weights_by_trial[tid]=w
            base[tid]=_run_weights(panel,w,1.0).reindex(oos).fillna(0.0); stressed[tid]=_run_weights(panel,w,2.0).reindex(oos).fillna(0.0); severe[tid]=_run_weights(panel,w,3.0).reindex(oos).fillna(0.0)
        except Exception as exc:
            failures.append({"trial_id":tid,"error":type(exc).__name__,"message":str(exc)}); z=pd.Series(0.0,index=oos); base[tid]=z; stressed[tid]=z; severe[tid]=z
    base_m=pd.DataFrame(base,index=oos).fillna(0.0); stress_m=pd.DataFrame(stressed,index=oos).fillna(0.0); severe_m=pd.DataFrame(severe,index=oos).fillna(0.0)
    synchronous=bool(base_m.index.equals(stress_m.index) and base_m.index.equals(severe_m.index) and not base_m.isna().any(axis=None));
    if not synchronous: raise RuntimeError("non-synchronous OOS matrices")
    metrics={tid:performance_metrics(base_m[tid]) for tid in base_m.columns}; dsr_benchmark=expected_max_sharpe([m["sharpe"] for m in metrics.values()]); dsr={}
    for tid,m in metrics.items():
        r=base_m[tid]; dsr[tid]=deflated_sharpe_probability(m["sharpe"],len(r),float(r.skew()),float(r.kurtosis()+3.0),dsr_benchmark)
    pbo=probability_of_backtest_overfitting(base_m,slices=8); ranked=sorted(base_m.columns,key=lambda t:(dsr[t],metrics[t]["sharpe"],metrics[t]["expectancy"]),reverse=True); winner=ranked[0]
    benchmarks=_benchmark_suite(panel,oos); benchmark_tests={}
    for name,bench in benchmarks.items():
        benchmark_tests[name]={"white":white_reality_check(base_m,bench,BootstrapConfig(samples=2000,block=20,seed=17,alpha=0.05)),"spa":hansen_spa(base_m,bench,SPAConfig(reps=2000,block_size=20,seed=29,alpha=0.05)),"paired":paired_block_bootstrap_superiority(base_m[winner],bench)}
    all_benchmarks_pass=all(v["white"].get("passed") and v["spa"].get("passed") and v["paired"].get("passed") for v in benchmark_tests.values())
    basic_regime=regime_stability_test(base_m[winner],_market_regime(panel).reindex(oos)); zero_weights=pd.DataFrame(0.0,index=panel.close.index,columns=panel.close.columns); winning_weights=weights_by_trial.get(winner,zero_weights)
    capacity=_capacity_evidence(panel,winning_weights,oos); portfolio=_portfolio_evidence(panel,winning_weights,oos)
    winner_stress=performance_metrics(stress_m[winner]); winner_severe=performance_metrics(severe_m[winner]); cost_survival=bool(metrics[winner]["expectancy"]>0 and winner_stress["expectancy"]>0 and metrics[winner]["total_return"]>0 and winner_stress["total_return"]>0)
    stats_pass=bool(dsr[winner]>=0.95 and np.isfinite(pbo.get("pbo",np.nan)) and pbo["pbo"]<=0.20 and all_benchmarks_pass)
    portfolio_pass=bool(portfolio["gross_limit_respected"] and portfolio["asset_limit_respected"] and portfolio["long_cash_only"] and portfolio["contribution_concentration_reasonable"])
    plateau=parameter_grid_plateau(trials=trials,metric_by_trial={k:v['sharpe'] for k,v in metrics.items()},winner_trial_id=winner); perturb=perturbation_suite(weights=winning_weights,oos_index=oos,run_fn=lambda w,m:_run_weights(panel,w,m))
    decomposition=regime_decomposition(returns=base_m[winner],btc_returns=_btc_benchmark(panel),cross_sectional_returns=panel.returns,aggregate_liquidity=panel.quote_volume.sum(axis=1,min_count=1)); cap_gate=capacity_gate(capacity)
    gate_results={
        "G6":{"status":"PASS" if not failures else "FAIL","reasons":[] if not failures else ["STRUCTURAL_TRIAL_EXECUTION_FAILURES"]},
        "G7":{"status":"PASS" if synchronous else "FAIL","reasons":[] if synchronous else ["NON_SYNCHRONOUS_OOS"]},
        "G8":{"status":"PASS" if stats_pass else "FAIL","reasons":[] if stats_pass else ["DSR_PBO_OR_MULTI_BENCHMARK_WHITE_SPA_BOOTSTRAP_GATE_FAILED"]},
        "G9":{"status":"PASS" if cost_survival else "FAIL","reasons":[] if cost_survival else ["BASE_OR_STRESSED_COST_SURVIVAL_FAILED"]},
        "G10":{"status":"PASS" if plateau.get('passed') and perturb.get('passed') else "FAIL","reasons":[] if plateau.get('passed') and perturb.get('passed') else ["PARAMETER_PLATEAU_OR_PERTURBATION_FAILED"]},
        "G11":{"status":"PASS" if decomposition.get('passed') and basic_regime.get('passed') else "FAIL","reasons":[] if decomposition.get('passed') and basic_regime.get('passed') else ["REGIME_STABILITY_OR_DECOMPOSITION_FAILED"]},
        "G12":{"status":"PASS" if cap_gate.get('passed') else "FAIL","reasons":[] if cap_gate.get('passed') else ["RESEARCH_CAPACITY_GATE_FAILED"]},
        "G13":{"status":"PASS" if portfolio_pass else "FAIL","reasons":[] if portfolio_pass else ["PORTFOLIO_RISK_OR_CONCENTRATION_LIMITS_FAILED"]},}
    classical_ml_admitted=bool(gate_results["G6"]["status"]=="PASS" and gate_results["G7"]["status"]=="PASS")
    evidence={"backtest_correctness":not failures,"one_bar_execution_delay":True,"point_in_time_features":True,"failed_trials_retained":True,"common_oos_folds":True,"purged":True,"embargoed":True,"oos_return_matrix_sha256":_sha256_bytes(base_m.to_csv().encode()),"dsr":dsr[winner],"pbo":pbo,"benchmark_tests":benchmark_tests,"base_costs":metrics[winner],"stressed_costs":winner_stress,"severe_costs":winner_severe,"research_cost_model":"15_30_45_BPS_ONE_WAY_CONSERVATIVE","parameter_plateau":plateau,"perturbations":perturb,"regime_decomposition":decomposition,"turnover":capacity,"capacity":cap_gate,"market_impact":"1_PERCENT_ADV_RESEARCH_PROXY_RECERTIFY_FOR_SCALE","portfolio_risk":portfolio}
    return {"schema_version":"1.3.0","stage":"STRUCTURAL_TOURNAMENT","trial_count_preregistered":registry["trial_count"],"trial_count_executed":len(trials),"trial_count_failed":len(failures),"failed_trials":failures,"winner":winner,"winner_family":next(t["family"] for t in trials if t["trial_id"]==winner),"winner_metrics":metrics[winner],"winner_dsr_probability":dsr[winner],"pbo":pbo,"benchmark_tests":benchmark_tests,"all_preregistered_benchmarks_pass":all_benchmarks_pass,"cost_stress_survived_base_and_stressed":cost_survival,"parameter_plateau":plateau,"perturbations":perturb,"regime_stability":basic_regime,"regime_decomposition":decomposition,"capacity":capacity,"capacity_gate":cap_gate,"portfolio":portfolio,"classical_ml_admitted":classical_ml_admitted,"deep_models_admitted":False,"holdout_opened":False,"holdout_evaluated":False,"paper_authorized":False,"testnet_authorized":False,"live_authorized":False,"gate_results":gate_results,"evidence":evidence,"decision":"ADMIT_CLASSICAL_ML" if classical_ml_admitted else "NO_EDGE_VERIFIED","base_oos_returns":base_m,"stressed_oos_returns":stress_m,"severe_oos_returns":severe_m}


def write_structural_tournament(result: dict[str, Any], output_dir: str | Path) -> None:
    root=Path(output_dir); root.mkdir(parents=True,exist_ok=True); serializable=dict(result); base=serializable.pop("base_oos_returns"); stressed=serializable.pop("stressed_oos_returns"); severe=serializable.pop("severe_oos_returns")
    base.to_csv(root/"structural-oos-base.csv"); stressed.to_csv(root/"structural-oos-stressed.csv"); severe.to_csv(root/"structural-oos-severe.csv")
    (root/"structural-tournament.json").write_text(json.dumps(serializable,indent=2,sort_keys=True,default=lambda x: float(x) if isinstance(x,np.generic) else str(x))+"\n",encoding="utf-8")
