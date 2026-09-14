from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
import numpy as np
import pandas as pd


class ForecastModel(Protocol):
    name: str
    def fit(self, x: pd.DataFrame, y: pd.Series) -> "ForecastModel": ...
    def predict(self, x: pd.DataFrame) -> pd.Series: ...


@dataclass
class RidgeForecaster:
    """Small deterministic baseline; model selection must beat this after costs."""
    alpha: float = 10.0
    name: str = "ridge"
    _beta: np.ndarray | None = None
    _columns: list[str] | None = None
    _mean: pd.Series | None = None
    _std: pd.Series | None = None

    def fit(self, x: pd.DataFrame, y: pd.Series) -> "RidgeForecaster":
        xy = x.join(y.rename("target"), how="inner").dropna()
        if len(xy) < max(50, x.shape[1] * 5):
            raise ValueError("insufficient training observations")
        xx = xy[x.columns].astype(float)
        self._columns = list(xx.columns)
        self._mean = xx.mean()
        self._std = xx.std(ddof=0).replace(0.0, 1.0)
        z = ((xx - self._mean) / self._std).to_numpy()
        design = np.column_stack([np.ones(len(z)), z])
        penalty = np.eye(design.shape[1]) * self.alpha
        penalty[0, 0] = 0.0
        self._beta = np.linalg.solve(design.T @ design + penalty, design.T @ xy["target"].to_numpy())
        return self

    def predict(self, x: pd.DataFrame) -> pd.Series:
        if self._beta is None or self._columns is None or self._mean is None or self._std is None:
            raise ValueError("model is not fitted")
        xx = x[self._columns].astype(float)
        z = ((xx - self._mean) / self._std).fillna(0.0).to_numpy()
        design = np.column_stack([np.ones(len(z)), z])
        return pd.Series(design @ self._beta, index=xx.index, name="forecast")


def forward_return(close: pd.Series, horizon: int = 1) -> pd.Series:
    """Training label only. Never include this column in features used at inference."""
    return close.shift(-horizon) / close - 1.0


def purged_train_test(
    index: pd.DatetimeIndex,
    train_end: pd.Timestamp,
    test_start: pd.Timestamp,
    test_end: pd.Timestamp,
    embargo_days: int = 7,
    label_horizon_days: int = 1,
) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """Create a leakage-resistant temporal split.

    Training observations are removed far enough from the test boundary that
    their forward-return labels cannot extend into the embargo or test period.
    This is stricter than merely separating feature timestamps.
    """
    if embargo_days < 0 or label_horizon_days < 1:
        raise ValueError("embargo_days must be >=0 and label_horizon_days must be >=1")
    boundary = test_start - pd.Timedelta(days=embargo_days + label_horizon_days)
    purge_end = min(train_end, boundary)
    train = index[index <= purge_end]
    test = index[(index >= test_start) & (index <= test_end)]
    if len(train) == 0 or len(test) == 0:
        raise ValueError("empty purged split")
    if train.max() + pd.Timedelta(days=label_horizon_days) >= test.min() - pd.Timedelta(days=embargo_days):
        raise ValueError("label horizon overlaps embargo/test boundary")
    return train, test


def model_candidate_registry() -> list[dict[str, object]]:
    """Candidates are hypotheses, not approved production models."""
    return [
        {"id": "ridge", "family": "linear", "status": "IMPLEMENTED_BASELINE", "requires": []},
        {"id": "hist_gradient_boosting", "family": "tree_boosting", "status": "CANDIDATE", "requires": ["scikit-learn"]},
        {"id": "xgboost", "family": "gradient_boosting", "status": "CANDIDATE", "requires": ["xgboost"]},
        {"id": "lstm", "family": "deep_learning", "status": "CHALLENGER_ONLY", "requires": ["torch"]},
        {"id": "itransformer", "family": "deep_learning", "status": "CHALLENGER_ONLY", "requires": ["torch"]},
        {"id": "llm_news_regime", "family": "llm", "status": "RESEARCH_ONLY", "requires": ["point_in_time_news_corpus"]},
    ]
