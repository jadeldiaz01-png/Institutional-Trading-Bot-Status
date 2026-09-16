# AR-TF Phase 2 — Video-Derived Quantitative Research Specification (2026)

## Purpose
Translate the concepts visible in the two reviewed trading videos into falsifiable, point-in-time quantitative hypotheses. This package is research-only. It does not modify the frozen 407-trial registry, current folds, current statistical thresholds, or the final 365-day holdout.

## Governance
Activation requires a terminal certificate from the current tournament: `NO_EDGE_VERIFIED` or `FROZEN_HOLDOUT_CANDIDATE`. Until then this package MUST NOT execute selection, open the holdout, authorize PAPER/TESTNET/LIVE, or alter the current tournament.

Every parameter combination counts as a trial. No parameter may be added after observing results in the same generation. DSR, PBO/CSCV, White Reality Check, Hansen SPA and paired block bootstrap must treat the full registered family as the multiplicity universe.

## Video concepts converted to research objects

### 1. Return dependence / autocorrelation
Concept: repeated directional behavior and return persistence.

Features:
- lagged return: `R_k(t)=P(t-1)/P(t-1-k)-1`
- lag-1 rolling autocorrelation: `rho_1(w)=Corr(r[t-w:t-1], r[t-w-1:t-2])`
- sign persistence: fraction of adjacent lagged returns with equal sign
- variance ratio for k={2,5,10}

Targets: 1d, 3d, 7d and 14d forward returns, evaluated only on preregistered OOS folds.

### 2. Objective market structure / breakout
Concept: price breaks an observable prior structure and may continue or retest.

Definitions:
- breakout level: prior rolling maximum high, excluding the signal bar
- breakout flag: `close(t-1) > max(high[t-L-1:t-2])`
- normalized breakout strength: `(close(t-1)-level)/ATR`
- retest distance: `(low(t-1)-level)/ATR`
- follow-through measured only after the signal and never used contemporaneously to create the signal

Execution: earliest permitted fill is the next bar. Same-bar fills are forbidden.

### 3. Path persistence
Concept: distinguish directional paths from noisy paths.

Features:
- path efficiency = absolute net movement / sum of absolute path movements
- directional consistency = absolute signed-return count / lookback
- drawdown from lagged rolling peak

Mandatory comparators: time-series momentum, Donchian breakout and BTC buy-and-hold where applicable.

### 4. Regime conditioning
Concept: test whether apparent patterns survive volatility/liquidity environments rather than relying on one chart regime.

Features:
- lagged realized volatility 20/60d
- trailing volatility percentile
- lagged 30d median quote volume
- cross-sectional liquidity percentile

Required slices: low/mid/high vol, low/high liquidity, bull/bear/sideways, year and asset.

### 5. Order flow / large-participant pressure
Concept: convert claims about large orders/market makers into observable microstructure variables.

This track is forbidden on daily OHLCV. It requires certified L2/book and trade data with exchange timestamps and sequence integrity.

Features:
- level-1 order-flow imbalance following bid/ask event changes
- normalized OFI by lagged depth scale
- aggressor-side trade imbalance
- quoted spread in bps
- bid/ask depth imbalance
- trade intensity

Forbidden proxies: candle colour, raw daily volume, or OHLCV-derived signed flow presented as true order flow.

## Metrics
Primary:
- net expectancy
- annualized Sharpe
- maximum drawdown
- turnover
- hit rate

Robustness:
- Deflated Sharpe Ratio probability
- PBO via CSCV
- White Reality Check
- Hansen SPA
- paired block-bootstrap confidence interval

Stability:
- parameter-plateau width
- fold/year/asset/regime pass fractions
- perturbation ±10%
- signal decay / half-life

Economics:
- BASE/STRESSED/SEVERE costs
- break-even cost in bps
- capacity estimate
- participation/impact constraints when execution size is material

## Admission gates
A candidate cannot advance unless all are true:
1. certified point-in-time data with unresolved_count=0;
2. preregistration completed before execution;
3. positive net OOS expectancy in BASE;
4. survival under STRESSED costs;
5. DSR >= 0.95;
6. PBO <= 0.20;
7. family-wide White RC and/or Hansen SPA gate passes under the frozen contract;
8. broad parameter plateau and perturbation stability;
9. regime/year/asset/liquidity stability;
10. strongest simple comparator is beaten after costs;
11. holdout remains untouched;
12. evidence bundle is reproducible and hash-bound.

Only two selection-stage terminal states are permitted: `NO_EDGE_VERIFIED` or `FROZEN_HOLDOUT_CANDIDATE`.

## Research-to-production boundary
These features do not directly create production orders. Any surviving alpha must later pass the separate execution-policy, latency, fill, adverse-selection, capacity, risk and production-readiness gates. PAPER, TESTNET and LIVE remain false by default.

## Files
- `config/ar_tf_phase2_video_hypotheses_2026.yaml`: preregistered hypotheses and gates.
- `src/ar_tf/phase2_video_features.py`: deterministic feature definitions.
- `tests/test_ar_tf_phase2_video_features.py`: lagging, boundedness and microstructure-data contracts.

## Literature anchors
The specification is informed by established evidence on time-series momentum, order-flow imbalance and data-snooping/backtest-overfitting controls. These sources motivate tests; they do not establish profitability in crypto or in this repository's dataset.
