# AR-TF v1-C — 2026 Alpha Research Protocol

## Status

RESEARCH only. This document does not claim profitability and does not authorize PAPER, TESTNET or LIVE. `LIVE_TRADING_ENABLED=false` remains mandatory.

## 2026 evidence incorporated as hypotheses

1. Bysik & Ślepaczuk (2026), *Machine Learning-Based Bitcoin Trading Under Transaction Costs: Evidence From Walk-Forward Forecasting* (arXiv:2606.00060 / SSRN 6795938): naive ML sign trading can fail after 10 bps costs; a cost-aware forecast threshold materially reduces turnover. XGBoost was descriptively stronger than LSTM/iTransformer in selected BTC experiments, without robust statistical dominance.
2. Kim & Lim (2026), *From Predictability to Tradability* (SSRN 7115197 and related preprint 6145964): deep-learning cross-sectional signals can be statistically detectable yet economically weak after transaction costs; no DL architecture is assumed to be superior.
3. Zhang & Makgolo (2026), *Cross-Sectional Dispersion and the State Dependence of Cryptocurrency Momentum* (SSRN 6648082): dynamic survivorship-aware universe construction matters; lagged cross-sectional dispersion is a candidate state variable for momentum degradation.
4. Kim (2026), *Beyond Accuracy: A Validation Framework for Machine Learning in Cryptocurrency Trading* (SSRN 6508779): accuracy alone is not a promotion criterion; CPCV/PBO, multiple-testing control, transaction costs and economic gates are mandatory.
5. Bieganowski & Ślepaczuk (2026), *Explainable Patterns in Cryptocurrency Microstructure* (arXiv:2602.00776): order-flow/spread/adverse-selection features are plausible execution-layer candidates, but they require point-in-time order-book data and are not inferred from daily OHLCV.
6. Binance Spot API changelog/documentation (accessed 2026-09-01): exchange filters/statuses evolve, including `CANCEL_ONLY`; execution research must snapshot applicable filters and not assume a timeless exchange state.

## Architecture under test

AR-TF remains the structural prior. ML/DL/LLM are challengers around it, not unchecked replacements.

`point-in-time universe -> causal features -> structural trend alpha -> dispersion regime scaler -> ML/DL challenger forecast -> uncertainty + cost-aware gate -> conservative alpha blend -> volatility/risk budget -> turnover limiter -> backtest with exchange frictions -> CPCV/PBO/DSR -> frozen holdout`

### Structural alpha

The existing multi-horizon trend/momentum signal remains the baseline because it is interpretable and testable over long histories.

### Dispersion regime overlay

Cross-sectional return dispersion is measured at each timestamp using only contemporaneously available returns. Elevated lagged dispersion reduces momentum allocation. The exact threshold is a hyperparameter and must enter the experiment registry.

### ML candidate hierarchy

Every model must beat simpler predecessors net of costs:

- Ridge: deterministic baseline.
- Histogram gradient boosting: first nonlinear challenger.
- XGBoost: external challenger motivated by 2026 BTC evidence.
- LSTM: challenger only.
- iTransformer/sequence Transformer: challenger only.
- Ensembles: allowed only after individual models are frozen and registered.

A complex model is rejected when its OOS improvement over a simpler model is not robust after costs and bootstrap uncertainty.

### Deep learning policy

DL is not allowed to see the frozen holdout during architecture selection. Hyperparameters, random seeds, feature sets and failed trials must be registered. Training must be deterministic where technically feasible and repeated across seeds otherwise.

### LLM policy

An LLM is **not** allowed to generate direct discretionary buy/sell decisions in this strategy. A possible LLM feature is a frozen, timestamped news/event regime score. It is admissible only when:

- the source corpus is stored with publication timestamps and immutable hashes;
- no revised/future articles leak backward;
- the exact prompt/model/version/temperature/output schema is recorded;
- an OHLCV-only baseline is tested in parallel;
- ablation proves incremental OOS economic value after data/API/model costs;
- unavailable LLM data fails closed rather than being silently imputed as bullish/bearish.

## Cost-aware execution gate

A forecast is tradable only when expected return exceeds estimated round-trip cost plus a minimum edge buffer plus a forecast-uncertainty margin. Cost estimates must eventually include fee tier, spread, slippage/impact and applicable Binance symbol filters. Cost stress remains mandatory at 1x/2x/3x.

## Required experiments

Before any PAPER_CANDIDATE decision, the experiment matrix must include at minimum:

- AR-TF baseline;
- AR-TF + dispersion scaling;
- Ridge only and AR-TF + Ridge;
- tree boosting/XGBoost only and blended;
- LSTM/iTransformer challengers if sufficient training data exists;
- cost-aware gate on/off ablation;
- turnover limiter on/off ablation;
- dynamic universe vs intentionally biased survivor-only diagnostic (the biased result may never certify);
- multiple horizons and neighboring parameter values;
- 1x/2x/3x costs and delayed fills;
- subperiod, regime, asset, liquidity and market-stress decomposition;
- CPCV/PBO, Deflated Sharpe, block bootstrap and Monte Carlo/path stress;
- benchmarks BTC buy-and-hold, equal-weight and simple trend.

## Promotion rule

No architecture is promoted because it has the highest backtest Sharpe. Selection requires a broad stable region, positive net expectancy OOS, acceptable drawdown/tail risk, cost survival, low enough PBO, DSR gate, benchmark-relative value and an untouched final holdout. The maximum automated result remains `PAPER_CANDIDATE`; human governance is still required.
