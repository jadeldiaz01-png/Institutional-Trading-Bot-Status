# AR-TF Edge Verification 2026

## Governing hypothesis

**NO EDGE VERIFIED UNTIL REPRODUCIBLE NET EVIDENCE EXISTS.**

External papers, platforms, strategy libraries, public backtests and community results are hypothesis generators only. They can influence what AR-TF tests, but they cannot certify AR-TF profitability.

The pre-holdout state space is intentionally limited to:

- `NO_EDGE_VERIFIED`
- `FROZEN_HOLDOUT_CANDIDATE`

Neither state authorizes PAPER, TESTNET or LIVE.

## Data comes before alpha

The tournament cannot start until the historical universe is point-in-time, survivorship-aware, checksum-verified, lifecycle-verified, free of unexplained gaps and unresolved duplicate conflicts, and cryptographically frozen with both lifecycle and dataset SHA-256 identities.

The final 365-day holdout is never used for feature engineering, model selection, parameter choice, cost calibration or strategy rejection during the tournament.

## 2026 research map

### High-priority OHLCV-compatible challengers

1. Time-series momentum / moving-average / Donchian trend.
2. Long/cash trend with volatility targeting tested both ON and OFF.
3. Cross-sectional momentum with a dynamic point-in-time universe.
4. Lagged cross-sectional dispersion as a momentum-breakdown state variable.
5. Price-path-continuity momentum: distinguish smooth continuation from jump-dominated past return.
6. Short-term and medium-horizon reversal, including volatility-conditioned reversal.
7. Volatility breakout and regime-aware breakout.
8. Simple structural ensembles.
9. Ridge as the first ML baseline.
10. Gradient boosting only after the linear baseline, using cost-aware trade filtering.

### Additional-data challengers

Funding carry, spot-perpetual basis, statistical arbitrage, intraday flow signals and volume/flow models require historical data beyond daily Spot OHLCV. They must not be approximated from unavailable information.

### Microstructure challengers

Order-book imbalance, queue-aware market making, adverse selection and depth-aware execution require trade/L2/L3 point-in-time data and a fill model. Bar-only backtests cannot verify these edges.

### Deferred complexity

LSTM, transformers, variational factor models and reinforcement learning are challenger classes, not defaults. They enter only after simple baselines and only if their incremental economic value remains positive after costs, multiplicity correction and ablations.

## Evidence incorporated into the hypothesis map

Research available through 2026 supports investigation of trend and momentum but also strongly warns against treating headline Sharpe as proof. Long-history evidence documents trend-following across asset classes, while crypto-specific 2026 studies report strong time-series momentum evidence but much weaker cross-sectional momentum under realistic assumptions. Recent work also identifies lagged cross-sectional dispersion as a candidate predictor of later crypto momentum deterioration.

New 2026 crypto research adds challengers rather than conclusions: volatility-conditioned cross-sectional reversal; price-path continuity; cost-aware XGBoost; adaptive trend/risk overlays; and microstructure features such as order-flow imbalance and spread. These are preregistered hypotheses and must compete on the same frozen dataset and folds where data requirements permit.

The strongest adversarial result is that naïve crypto factor evaluation can materially inflate apparent Sharpe. A 2026 audit of standard crypto factors found approximately 3.6x average Sharpe inflation when comparing naïve full-sample/frictionless evaluation with nested walk-forward, costs and multiplicity-aware validation; none of the audited factors survived the study's baseline deflation protocol. This is a direct design requirement for AR-TF's fail-closed tournament.

## Research-platform knowledge

QuantConnect's research guidance reinforces hypothesis-first research, explicit out-of-sample periods and avoidance of parameter-driven hypothesis creation. Hudson & Thames/mlfinlab provides established implementations and references for backtest-overfitting controls such as Deflated Sharpe and related selection diagnostics. NautilusTrader's fill-model documentation is a useful execution-model reference because it makes explicit that historical bars/books do not reveal a strategy's true queue interaction and that fill probability/slippage assumptions must be modeled.

These platforms are implementation and methodology references; their strategy results are not imported as AR-TF evidence.

## Tournament contract

Before execution, register every candidate, parameter grid, seed and exclusion. Failed trials remain in the experiment ledger. All competing trials use exactly the same OOS timestamps. The number of attempted trials is part of multiplicity adjustment.

Every eligible candidate must be evaluated under:

- rolling and, where appropriate, anchored walk-forward;
- purging and embargo for overlapping labels/features;
- BASE, STRESSED and SEVERE execution-cost scenarios;
- BTC buy-and-hold, equal-weight point-in-time universe and simple trend benchmarks;
- block bootstrap and Monte Carlo;
- Deflated Sharpe Ratio;
- CSCV/PBO;
- White Reality Check and/or Hansen SPA;
- parameter perturbation / plateau tests;
- entry/execution delay;
- randomized slippage and missing-trade stress;
- fee/spread/liquidity deterioration;
- delisting/terminal-return stress;
- year, asset, regime, volatility, liquidity and dispersion decomposition.

A strategy is rejected when its apparent edge is concentrated in a narrow parameter spike, one year, one coin, one regime, one cost assumption or one execution convention.

## Cost-aware alpha requirement

Forecast accuracy is not an edge. The economically relevant object is the return distribution after the decision rule, turnover, fees, spread, slippage, impact, latency, partial fills, rejects, exchange filters, rounding and liquidity limits.

High-frequency models must include a no-trade region or another preregistered decision rule when predicted edge does not exceed estimated execution friction. Any threshold itself belongs to the registered research grid and is subject to multiplicity correction.

## Causal-story requirement

Labels such as trend, momentum or mean reversion are not economic mechanisms. Each promoted hypothesis must record a plausible causal or behavioral mechanism, expected failure regime, crowding/capacity mechanism and falsification test. Mechanism plausibility does not substitute for statistics, but strategies with no coherent mechanism receive greater prior skepticism.

## Edge-verification gate

Before the final holdout, an AR-TF candidate may reach `FROZEN_HOLDOUT_CANDIDATE` only if all of the following are true:

- frozen dataset and lifecycle SHA identities exist;
- zero unresolved data defects;
- all trials were preregistered and counted;
- common OOS folds/timestamps were used;
- net OOS expectancy, compounded growth and Sharpe are positive;
- DSR probability >= 0.95;
- PBO <= 0.20;
- multiplicity-aware benchmark test supports the candidate;
- candidate beats preregistered benchmarks on economically relevant metrics;
- BASE and STRESSED costs remain viable;
- robustness/parameter plateau tests pass;
- regime and liquidity/capacity evidence do not reveal a single-regime artifact.

Only then may exactly one frozen candidate be evaluated once on the untouched holdout. Holdout failure means `NO_EDGE_VERIFIED`; it does not trigger retuning against the holdout.

## Forward evidence

A successful holdout is not a live-trading certificate. PAPER must measure forward expectancy and model drift with no capital. TESTNET must validate exchange behavior, order state, filters, idempotency, UNKNOWN-state recovery, reconciliation and execution-quality telemetry. LIVE_PILOT requires explicit human approval, bounded capital, stable forward evidence, no unreconciled orders and operational/risk gates.

## Current AR-TF implication

The immediate blocker remains data certification, not strategy quantity. The unresolved Binance archive duplicate-timestamp defects must be reconciled scientifically, the dataset frozen, and only then can this expanded hypothesis library enter the v1-D tournament. Until that happens, the only valid conclusion remains `NO_EDGE_VERIFIED`.
