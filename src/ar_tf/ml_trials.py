from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import yaml
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from .research_panel import ResearchPanel, inverse_vol_weights, rolling_liquidity_universe
from .ridge_fold_resume import checkpoint_manifest_path, commit_fold_checkpoint, load_committed_fold


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
        # pandas 3 removed support for explicitly passing dropna to the new
        # stack implementation. Missing feature rows are removed deterministically
        # by the frame-level dropna below, so leaving stack() unspecified preserves
        # the intended complete-case semantics across pandas 2.x/3.x.
        pieces.append(value.reindex(dates).stack().rename(name))
    frame=pd.concat(pieces,axis=1).replace([np.inf,-np.inf],np.nan).dropna()
    frame.index.names=["timestamp","market_id"]
    return frame


def _long_training_frame(features: dict[str, pd.DataFrame], target: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    x=_long_features(features,dates)
    y=target.reindex(dates).stack().rename("target")
    # pandas does not consistently propagate index/column names through stack()
    # across 2.x/3.x. Naming the MultiIndex explicitly is metadata-only and keeps
    # the frozen row identity/order while making the join version-stable.
    y.index.names=["timestamp","market_id"]
    return x.join(y,how="inner").replace([np.inf,-np.inf],np.nan).dropna()


def _future_return(panel: ResearchPanel, horizon: int) -> pd.DataFrame:
    return panel.close.shift(-horizon) / panel.close - 1.0


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return [_jsonable(v) for v in value.tolist()]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _series_to_rows(series: pd.Series) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for (timestamp, market_id), value in series.sort_index().items():
        v = float(value)
        rows.append([pd.Timestamp(timestamp).isoformat(), str(market_id), v if np.isfinite(v) else None])
    return rows


def _rows_to_series(rows: list[list[Any]]) -> pd.Series:
    tuples: list[tuple[pd.Timestamp, str]] = []
    values: list[float] = []
    for timestamp, market_id, value in rows:
        tuples.append((pd.Timestamp(timestamp), str(market_id)))
        values.append(float("nan") if value is None else float(value))
    index = pd.MultiIndex.from_tuples(tuples, names=["timestamp", "market_id"])
    return pd.Series(values, index=index, dtype=float)


def _execute_walk_forward_fold(
    *,
    panel: ResearchPanel,
    fold: dict[str, Any],
    features: dict[str, pd.DataFrame],
    target: pd.DataFrame,
    family: str,
    params: dict[str, Any],
    seed: int,
    rng: np.random.Generator,
    max_training_rows_per_fold: int,
) -> tuple[pd.Series, pd.Series, int, int]:
    horizon=int(params["horizon_days"])
    train_start=pd.Timestamp(fold["train_start"],tz="UTC")
    train_end=pd.Timestamp(fold["train_end"],tz="UTC")
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
        return pd.Series(dtype=float), pd.Series(dtype=float), 0, 0
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
    return pd.Series(pred,index=idx), pd.Series(residual_scale,index=idx), len(train), len(test)


def walk_forward_predictions(
    panel: ResearchPanel,
    folds_path: str | Path,
    *,
    family: str,
    params: dict[str, Any],
    seed: int,
    max_training_rows_per_fold: int = 200_000,
    checkpoint_root: str | Path | None = None,
    checkpoint_trial_id: str | None = None,
    checkpoint_lineage: Mapping[str, Any] | None = None,
    stop_after_fold: int | None = None,
) -> MLPrediction:
    """Walk-forward prediction with optional transactional fold resume.

    Checkpoint mode does not alter the scientific path: features, targets, fold
    order, fitting, preprocessing, sampling and model parameters remain the same.
    A committed fold is reused only after state, lineage and digest validation;
    its exact RNG-after state becomes the RNG-before state of the next fold.
    """
    horizon=int(params["horizon_days"])
    if horizon < 1:
        raise ValueError("horizon_days must be positive")
    folds=_folds(folds_path)
    if stop_after_fold is not None and (stop_after_fold < 0 or stop_after_fold >= len(folds)):
        raise ValueError("stop_after_fold out of range")
    checkpoint_requested = any(v is not None for v in (checkpoint_root, checkpoint_trial_id, checkpoint_lineage, stop_after_fold))
    if checkpoint_requested and (checkpoint_root is None or checkpoint_trial_id is None or checkpoint_lineage is None):
        raise ValueError("checkpoint_root, checkpoint_trial_id and checkpoint_lineage are required together")

    features=_feature_panels(panel)
    target=_future_return(panel,horizon)
    forecasts=[]; uncertainties=[]
    total_train=0; total_pred=0
    rng=np.random.default_rng(int(seed))

    for fold_index,fold in enumerate(folds):
        rng_state_before=_jsonable(rng.bit_generator.state)
        payload: dict[str, Any] | None = None
        manifest_path: Path | None = None

        if checkpoint_requested:
            manifest_path=checkpoint_manifest_path(checkpoint_root, str(checkpoint_trial_id), fold_index)
            if manifest_path.is_file():
                payload=load_committed_fold(
                    manifest_path,
                    expected_trial_id=str(checkpoint_trial_id),
                    expected_fold_id=fold_index,
                    expected_lineage=dict(checkpoint_lineage),
                )
                if payload.get("rng_state_before") != rng_state_before:
                    raise ValueError("checkpoint RNG state-before mismatch")
                if payload.get("fold_spec") != _jsonable(fold):
                    raise ValueError("checkpoint fold specification mismatch")
                rng.bit_generator.state=payload["rng_state_after"]

        if payload is None:
            forecast,uncertainty,training_rows,prediction_rows=_execute_walk_forward_fold(
                panel=panel, fold=fold, features=features, target=target, family=family,
                params=params, seed=int(seed), rng=rng,
                max_training_rows_per_fold=max_training_rows_per_fold,
            )
            if checkpoint_requested:
                payload={
                    "schema_version":"1.0.0",
                    "fold_id":fold_index,
                    "fold_spec":_jsonable(fold),
                    "forecast":_series_to_rows(forecast),
                    "uncertainty":_series_to_rows(uncertainty),
                    "training_rows":int(training_rows),
                    "prediction_rows":int(prediction_rows),
                    "rng_state_before":rng_state_before,
                    "rng_state_after":_jsonable(rng.bit_generator.state),
                }
                manifest_path=commit_fold_checkpoint(
                    checkpoint_root,
                    trial_id=str(checkpoint_trial_id),
                    fold_id=fold_index,
                    lineage=dict(checkpoint_lineage),
                    payload=payload,
                )
                payload=load_committed_fold(
                    manifest_path,
                    expected_trial_id=str(checkpoint_trial_id),
                    expected_fold_id=fold_index,
                    expected_lineage=dict(checkpoint_lineage),
                )
                if payload.get("rng_state_before") != rng_state_before:
                    raise ValueError("committed checkpoint RNG state-before mismatch")
                rng.bit_generator.state=payload["rng_state_after"]
                forecast=_rows_to_series(payload["forecast"])
                uncertainty=_rows_to_series(payload["uncertainty"])
                training_rows=int(payload["training_rows"])
                prediction_rows=int(payload["prediction_rows"])
        else:
            forecast=_rows_to_series(payload["forecast"])
            uncertainty=_rows_to_series(payload["uncertainty"])
            training_rows=int(payload["training_rows"])
            prediction_rows=int(payload["prediction_rows"])

        if not forecast.empty:
            forecasts.append(forecast)
            uncertainties.append(uncertainty)
        total_train+=int(training_rows)
        total_pred+=int(prediction_rows)

        if stop_after_fold is not None and fold_index >= stop_after_fold:
            break

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
