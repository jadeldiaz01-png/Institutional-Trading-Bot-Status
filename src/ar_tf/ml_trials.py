from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from .research_panel import ResearchPanel, inverse_vol_weights, rolling_liquidity_universe


@dataclass(frozen=True)
class MLPrediction:
    forecast: pd.DataFrame
    uncertainty: pd.DataFrame
    training_rows: int
    prediction_rows: int


def _folds(path: str | Path) -> list[dict[str, Any]]:
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return list(cfg["walk_forward"]["folds"])


def _feature_panels(panel: ResearchPanel) -> dict[str, pd.DataFrame]:
    close = panel.close
    r = panel.returns
    qv = panel.quote_volume
    med_qv = qv.shift(1).rolling(30, min_periods=10).median()
    liquidity_rank = med_qv.rank(axis=1, pct=True)
    return {
        "ret_1": r.shift(1),
        "ret_7": close.shift(1) / close.shift(8) - 1.0,
        "ret_30": close.shift(1) / close.shift(31) - 1.0,
        "ret_90": close.shift(1) / close.shift(91) - 1.0,
        "vol_30": r.shift(1).rolling(30, min_periods=20).std(),
        "downside_30": r.shift(1).clip(upper=0.0).rolling(30, min_periods=20).std(),
        "liquidity_rank": liquidity_rank,
    }


def _long_features(features: dict[str, pd.DataFrame], dates: pd.DatetimeIndex) -> pd.DataFrame:
    pieces=[]
    for name,value in features.items():
        pieces.append(value.reindex(dates).stack(dropna=False).rename(name))
    frame=pd.concat(pieces,axis=1).replace([np.inf,-np.inf],np.nan).dropna()
    frame.index.names=["timestamp","market_id"]
    return frame


def _long_training_frame(features: dict[str, pd.DataFrame], target: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    x=_long_features(features,dates)
    y=target.reindex(dates).stack(dropna=False).rename("target")
    return x.join(y,how="inner").replace([np.inf,-np.inf],np.nan).dropna()


def _future_return(panel: ResearchPanel, horizon: int) -> pd.DataFrame:
    return panel.close.shift(-horizon) / panel.close - 1.0


def walk_forward_predictions(
    panel: ResearchPanel,
    folds_path: str | Path,
    *,
    family: str,
    params: dict[str, Any],
    seed: int,
    max_training_rows_per_fold: int = 200_000,
) -> MLPrediction:
    horizon=int(params["horizon_days"])
    if horizon < 1:
        raise ValueError("horizon_days must be positive")
    features=_feature_panels(panel)
    target=_future_return(panel,horizon)
    forecasts=[]; uncertainties=[]
    total_train=0; total_pred=0
    rng=np.random.default_rng(int(seed))

    for fold in _folds(folds_path):
        train_start=pd.Timestamp(fold["train_start"],tz="UTC")
        train_end=pd.Timestamp(fold["train_end"],tz="UTC")
        # Purge any training label whose future-return horizon would cross the
        # declared training boundary. Embargo begins only after this purged end.
        effective_train_end=train_end-pd.Timedelta(days=horizon)
        test_start=pd.Timestamp(fold["test_start"],tz="UTC")
        test_end=pd.Timestamp(fold["test_end"],tz="UTC")
        if effective_train_end < train_start:
            raise ValueError("horizon consumes entire training fold")
        train_dates=panel.close.index[(panel.close.index>=train_start)&(panel.close.index<=effective_train_end)]
        test_dates=panel.close.index[(panel.close.index>=test_start)&(panel.close.index<=test_end)]
        train=_long_training_frame(features,target,train_dates)
        test=_long_features(features,test_dates)
        if train.empty or test.empty:
            continue
        if len(train)>max_training_rows_per_fold:
            take=np.sort(rng.choice(len(train),size=max_training_rows_per_fold,replace=False))
            train=train.iloc[take]
        X=train.drop(columns="target").to_numpy(float); y=train["target"].to_numpy(float)
        Xtest=test.to_numpy(float)
        scaler=StandardScaler().fit(X)
        Xs=scaler.transform(X); Xts=scaler.transform(Xtest)

        if family=="ridge":
            model=Ridge(alpha=float(params["alpha"]),fit_intercept=True)
            model.fit(Xs,y)
        elif family=="gradient_boosting_cost_aware":
            model=HistGradientBoostingRegressor(
                max_depth=int(params["max_depth"]), learning_rate=float(params["learning_rate"]),
                max_iter=100, l2_regularization=1e-3, random_state=int(seed), early_stopping=True,
            )
            model.fit(Xs,y)
        else:
            raise ValueError(f"unsupported ML family: {family}")

        pred=np.asarray(model.predict(Xts),dtype=float)
        train_pred=np.asarray(model.predict(Xs),dtype=float)
        residual_scale=float(np.nanstd(y-train_pred,ddof=1)) if len(y)>2 else float("nan")
        idx=test.index
        forecasts.append(pd.Series(pred,index=idx))
        uncertainties.append(pd.Series(residual_scale,index=idx))
        total_train+=len(train); total_pred+=len(test)

    if not forecasts:
        raise ValueError("no walk-forward predictions produced")
    f=pd.concat(forecasts).groupby(level=[0,1]).last().unstack("market_id").sort_index()
    u=pd.concat(uncertainties).groupby(level=[0,1]).last().unstack("market_id").sort_index()
    if bool((f.index >= panel.holdout_start).any()):
        raise RuntimeError("ML prediction leaked into final holdout")
    return MLPrediction(forecast=f,uncertainty=u,training_rows=total_train,prediction_rows=total_pred)


def prediction_to_weights(panel: ResearchPanel, prediction: MLPrediction, *, cost_gate_bps: float, universe_size: int = 15) -> pd.DataFrame:
    universe=rolling_liquidity_universe(panel,max_assets=universe_size).reindex(prediction.forecast.index).fillna(False)
    threshold=float(cost_gate_bps)/10_000.0 + prediction.uncertainty.abs()
    eligible=(prediction.forecast>threshold) & universe
    score=prediction.forecast.clip(lower=0.0).where(eligible,0.0)
    weights=inverse_vol_weights(score,panel.returns.reindex(score.index))
    return weights.reindex(panel.close.index).fillna(0.0)
