# AR-TF v1-D — Quantitative Model Tournament

Status: `RESEARCH / NO_GO`

This stage exists to determine whether any candidate architecture adds robust, net, out-of-sample value after realistic trading frictions. It is not a search for the highest backtest Sharpe and it does not authorize PAPER, TESTNET, LIVE_PILOT, or capital deployment.

## Core rule

The frozen final 365-day holdout is not available to model development, ranking, feature selection, hyperparameter tuning, threshold selection, cost calibration, or model-family selection. Tournament output can only be `NO_GO` or `FROZEN_HOLDOUT_CANDIDATE`.

## Candidate families

The preregistered progression is:

1. structural AR-TF baseline
2. structural AR-TF + dispersion scaler
3. Ridge baseline
4. histogram gradient boosting
5. XGBoost
6. LSTM challenger
7. iTransformer challenger
8. ensembles only if simpler candidates establish incremental OOS value
9. LLM news regime only after an immutable point-in-time news corpus exists

Complexity is rejected unless it improves economic and statistical robustness on exactly the same folds.

## Required evidence

Every registered trial must preserve dataset manifest SHA-256, lifecycle metadata SHA-256, code SHA, parameters, seed, folds, OOS returns, stress returns, metrics, and completion/failure state. Failed and weak trials remain in the registry so multiple-testing penalties cannot be reduced by deleting experiments.

All candidate returns used for PBO must be synchronous. PBO is computed across competing trials. DSR uses the total number of registered trials. Cost stress is evaluated at 1x, 2x, and 3x. Missing/non-finite PBO or DSR fails closed.

## Selection policy

A candidate must simultaneously satisfy:

- positive net OOS expectancy
- positive net OOS Sharpe
- DSR probability >= 0.95
- PBO <= 0.20
- positive expectancy under every required cost-stress scenario
- identical OOS timestamps for all compared trials
- no access to final holdout

Eligible candidates are ranked robustness-first: DSR, then net OOS Sharpe, then net OOS expectancy. Selection on headline Sharpe alone is prohibited.

## Point-in-time universe requirement

Real historical execution remains invalid until a credible historical Binance Spot lifecycle dataset is supplied. Current exchange listings cannot be used to reconstruct the past universe because that creates survivorship bias. The downloader now includes mid-month listing/delisting overlap so lifecycle events are not silently omitted.

The example lifecycle CSV is test data only and must never produce research certification evidence.

## Real-data execution gate

The historical tournament may start only when all of the following exist:

- real lifecycle CSV with source/provenance
- lifecycle metadata digest
- Binance Vision market history downloaded for lifecycle-overlapping periods
- dataset manifest with point-in-time declaration and digest
- common walk-forward folds
- registered candidate matrix
- benchmark returns

Until then the correct decision is `NO_GO: HISTORICAL_LIFECYCLE_EVIDENCE_MISSING`.

## No profitability claim

No result from code presence, unit tests, synthetic fixtures, CI success, or model availability is evidence of profitability. Profitability can only be discussed after reproducible real-data OOS results and the single untouched holdout are available, with all costs and statistical-selection penalties included.
