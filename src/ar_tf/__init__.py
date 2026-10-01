"""AR-TF v1 quantitative research package. Research-only; no live execution."""

from .core import ResearchConfig, build_features, build_signal, classify_regime, portfolio_weights
from .validation import performance_metrics, bootstrap_sharpe, monte_carlo_drawdowns, deflated_sharpe_probability, certification_decision

__all__ = [
    "ResearchConfig", "build_features", "build_signal", "classify_regime", "portfolio_weights",
    "performance_metrics", "bootstrap_sharpe", "monte_carlo_drawdowns", "deflated_sharpe_probability", "certification_decision",
]
