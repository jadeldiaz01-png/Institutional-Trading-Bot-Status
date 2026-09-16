# AR-TF Production Strategy Research Phase 2 — 2026-09-15

## Governance

This document is a post-current-tournament research backlog. It MUST NOT mutate the frozen 407-trial preregistration, current G4-G13 thresholds, common folds, or the untouched 365-day holdout. External literature generates hypotheses only. No strategy in this file is authorized for PAPER, TESTNET, LIVE_PILOT, or LIVE.

Current admissible pre-holdout decisions remain:

- `NO_EDGE_VERIFIED`
- `FROZEN_HOLDOUT_CANDIDATE`

`LIVE_TRADING_ENABLED=false` remains mandatory.

## 1. Momentum hierarchy: prioritize TSMOM over XSMOM as a challenger ordering, not as a conclusion

Recent evidence is mixed but materially more cautious on cross-sectional momentum. A 2026 net-of-costs replication on tradable Binance perpetuals found the tested cross-sectional momentum spreads not statistically distinguishable from zero after realistic costs, while a 2026 revision accepted in the Review of Asset Pricing Studies reports stronger evidence for time-series momentum and almost no cross-sectional momentum under more realistic assumptions.

Research action after the current tournament is frozen:

- TSMOM long/cash and long/flat baselines become the first momentum challengers.
- XSMOM remains a challenger but receives no evidentiary preference.
- Compare both under identical PIT universe, folds, turnover budgets, BASE/STRESSED/SEVERE costs, and the same multiple-testing stack.
- Reject any momentum family that only works gross of fees or only on one rebalance phase.

References:
- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7404139
- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4675565

## 2. Dispersion and path continuity as state variables, not post-hoc filters

Retain lagged cross-sectional dispersion and price-path continuity as preregistered interaction variables. Do not add thresholds after inspecting OOS results. Require ablations:

- raw momentum/reversal baseline;
- + dispersion state;
- + path continuity;
- + volatility interaction;
- full interaction model.

Any incremental value must survive paired OOS bootstrap and multiplicity adjustment.

References:
- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6648082

## 3. Intraday liquidity/session state

2026 evidence shows that volatility is a primary driver of spread variation and that intraday liquidity periodicity remains relevant in crypto despite 24/7 trading. Stablecoin market quality can also vary materially by session/weekend.

This is a separate data track. Daily bars are insufficient to claim intraday execution alpha.

Required data before testing:

- timestamped trades;
- best bid/ask and depth snapshots;
- exchange clock drift evidence;
- session labels (UTC, Asia, Europe, US, weekend);
- realized spread, quoted spread, depth-adjusted spread, Amihud/Kyle-style impact estimates;
- trade-size and participation-rate metadata.

Research hypotheses:

- session-aware no-trade regions;
- liquidity-conditioned execution urgency;
- volatility x spread interaction for expected implementation shortfall;
- weekend liquidity penalty.

References:
- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6401099
- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6778618

## 4. Order-flow imbalance / microstructure challengers

Recent microstructure research reports predictive content in liquidity, price-discovery and order-flow variables, but contemporaneous mechanical price impact must be separated from genuine forward prediction.

Required protocol:

- use strictly lagged OFI features;
- predict future returns after the feature interval, never same-interval returns;
- include spread, depth, volatility and trade intensity controls;
- evaluate maker and taker economics separately;
- include queue/fill uncertainty and adverse-selection costs;
- require feature ablation and cross-period stability.

This track is forbidden on daily OHLCV-only data.

References:
- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4814346
- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6938742
- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6057134

## 5. Portfolio construction: treat HRP/risk parity as risk allocators, not alpha

A 2026 survivorship-aware Binance study reports HRP-family variants tightly clustered and not significantly superior under SPA across a large parameter sweep. Therefore HRP, NCO, risk parity and volatility targeting are portfolio/risk overlays; they do not receive alpha credit.

Required comparisons:

- equal risk / inverse vol baseline;
- capped equal weight;
- HRP variants;
- correlation-clustered risk budgets;
- signal-weighted versions only after standalone signal edge is verified.

Reject any allocator whose benefit is only parameter-specific or whose turnover/costs erase the improvement.

References:
- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7157403

## 6. Volatility targeting must be asset-specific

Do not assume that higher volatility always requires lower exposure. Recent evidence suggests volatility-state effects on trend performance can be asset-dependent.

Protocol:

- compare fixed exposure, inverse-vol scaling, capped inverse-vol, and regime-conditioned scaling;
- test interaction between forecast edge and volatility, not only volatility itself;
- classify drawdown reduction separately from alpha improvement.

Reference:
- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6444878

## 7. Execution layer: use modern Binance primitives only after TESTNET evidence

Binance Spot currently documents BBO, TWAP, POV, OCO/OTO/OTOCO, STP, pegged orders, SOR fields, partial fills, and explicit expiry reasons. These are execution tools, not alpha.

Execution research matrix for TESTNET/SHADOW only:

- LIMIT/GTC baseline;
- post-only maker baseline;
- BBO queue vs counterparty placement;
- TWAP for large orders;
- POV for volume-participation execution;
- OCO/OTOCO protective order semantics;
- STP behavior;
- SOR/workingFloor telemetry when available;
- partial-fill and amend/cancel state machine;
- rate-limit exhaustion and websocket gap recovery.

Measure implementation shortfall, fill ratio, reject rate, partial-fill ratio, maker/taker mix, latency p50/p95/p99, spread capture and adverse selection. Do not assume successful API acknowledgement means execution success.

References:
- https://www.binance.com/en/support/faq/detail/3930d66642a947ff99bc8da5cefbca43
- https://www.binance.com/en/support/faq/detail/b5b7a1b4182b4cd696454da2e0629687
- https://www.binance.com/en/support/faq/detail/17b4a2b62c254141856df4f816ca1b51
- https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/ws-api/account
- https://developers.binance.com/en/docs/products/spot/faqs/spot_glossary

## 8. Cost model hardening

Binance Spot regular-user headline fees are currently 10 bps maker / 10 bps taker before any account-specific discount; actual fees vary by VIP level and promotions. Therefore the research engine must not hard-code promotional or BNB-discount assumptions.

Cost scenarios must include:

BASE:
- current non-promotional account fee schedule retrieved at runtime or pinned as dated evidence;
- half-spread / realized slippage estimate by liquidity bucket;
- rounding/min-notional effects.

STRESSED:
- fee schedule without discounts;
- wider spread and higher slippage;
- lower fill probability / more partial fills.

SEVERE:
- tail spread/impact based on historical stress quantiles;
- delayed fills and rejections;
- venue degradation / data gaps.

Reference:
- https://www.binance.com/en/fee/trading

## 9. Capacity and market impact gate

Before PAPER promotion, every candidate must estimate capacity under participation constraints.

Minimum tests:

- order size / ADV;
- order size / visible depth;
- participation-rate sweep;
- square-root or empirically fitted impact curve with uncertainty bands;
- concentration by symbol and liquidity bucket;
- stress-day capacity.

A strategy with positive net edge only at de minimis size is not production-ready; a strategy that requires excessive participation is rejected.

## 10. Funding/carry as a separate future sleeve

Funding/basis ideas must remain outside the current spot strategy tournament until funding histories, contract specifications, liquidation mechanics, collateral, borrow, and basis data are separately certified. Published carry results are not transferable proof.

No leverage or derivatives may be enabled by this document.

## 11. Production strategy admission contract

A strategy may be labeled `FROZEN_HOLDOUT_CANDIDATE` only if all are true:

1. Frozen dataset and scope binding verified.
2. Hypothesis preregistered before OOS inspection.
3. Net positive OOS expectancy under BASE costs.
4. Survives STRESSED costs with economically plausible capacity.
5. DSR >= configured gate.
6. PBO <= configured gate.
7. White Reality Check / Hansen SPA family evidence passes.
8. Parameter plateau is broad, not an isolated optimum.
9. Regime/year/asset/liquidity decomposition is not dominated by one slice.
10. Seed stability passes for stochastic models.
11. Strongest simple baseline is beaten on the same folds.
12. No holdout access occurred.
13. Reproducible artifact hashes, code SHA, dataset SHA, config SHA and seeds are retained.

Even then:

- `paper_authorized=false`
- `testnet_authorized=false`
- `live_authorized=false`

Promotion to PAPER remains a separate human-governed workflow.

## 12. Current recommendation

Do not mutate the active 407-trial tournament in PR #9. Finish the frozen experiment exactly as preregistered. This Phase 2 backlog becomes eligible only after the current tournament has a terminal, reproducible certificate (`NO_EDGE_VERIFIED` or `FROZEN_HOLDOUT_CANDIDATE`).
