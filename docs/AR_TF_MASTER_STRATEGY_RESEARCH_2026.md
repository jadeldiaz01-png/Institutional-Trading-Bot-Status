# AR-TF Master Strategy Research Program 2026

## Governing principle

NO EDGE IS VERIFIED UNTIL THE FROZEN INTERNAL DATASET PRODUCES REPRODUCIBLE, NET-OF-COST, MULTIPLICITY-ADJUSTED OUT-OF-SAMPLE EVIDENCE.

The objective is not to tune until a requested return appears. That procedure is a direct generator of selection bias. The objective is to search broadly, preregister the search space, count every attempt, and reject hypotheses that do not survive.

## Evidence hierarchy

1. External research and public repositories: hypothesis generation only.
2. Internal training/validation: model development only.
3. Common walk-forward OOS: candidate comparison.
4. Multiplicity-adjusted tournament: DSR, PBO, White RC / SPA, paired benchmark tests.
5. One untouched 365-day holdout: one-time confirmation only.
6. PAPER forward evidence: no capital.
7. TESTNET / SHADOW: execution and reconciliation evidence.
8. LIVE_PILOT: separate human authorization and bounded operational-risk gate.

## 2026 findings converted into testable hypotheses

### Cost-aware machine learning

Bysik and Slepaczuk (2026) test XGBoost, LSTM and iTransformer on roughly 70,000 hourly BTC/USDT observations with 27-fold walk-forward evaluation. Naive sign strategies fail under 10 bps transaction costs; selected cost-aware filters materially reduce turnover and recover positive results. The study reports XGBoost as descriptively strongest, but bootstrap evidence does not establish formal dominance over neural alternatives.

AR-TF consequence: forecast accuracy is not an admission metric. XGBoost/LSTM/Transformer candidates require a preregistered no-trade region tied to estimated costs and uncertainty, and must beat the simplest economically viable baseline on the same folds and features.

Reference: Bysik & Slepaczuk, Machine Learning-Based Bitcoin Trading Under Transaction Costs, 2026, SSRN 6795938 / arXiv 2606.00060.

### ML predictability versus tradability

Kim and Lim (2026) explicitly separate predictive signal from tradable portfolio performance under fixed information, implementation timing and transaction costs. This supports an evaluation ladder from forecasting metrics to net economic performance rather than treating classification accuracy or IC as an edge certificate.

Reference: Kim & Lim, From Predictability to Tradability, 2026, SSRN 7115197.

### Momentum breakdown state

Zhang and Makgolo (2026) reconstruct a dynamic, survivorship-aware crypto universe and find lagged cross-sectional dispersion associated with subsequent weakening of momentum, even after controls for Bitcoin realized volatility and average cross-asset correlation.

AR-TF consequence: lagged dispersion is a preregistered state variable and an ablation target, not a free post-hoc filter.

Reference: Zhang & Makgolo, Cross-Sectional Dispersion and the State Dependence of Cryptocurrency Momentum, 2026, SSRN 6648082.

### Reversal challenger

Kiefer and Nowotny (2026) report cross-sectional reversal over 8-10 week formation windows in Binance USDT spot, stronger in higher-volatility and non-largest assets, with delisting-aware treatment and block-bootstrap evidence.

AR-TF consequence: add medium-horizon reversal and volatility-conditioned reversal as challengers using the point-in-time universe; do not import the published parameters as proof.

Reference: Kiefer & Nowotny, Reversal in Cryptocurrency Returns, 2026, SSRN 6703978.

### Price-path continuity

Kim (2026) reports that short-term returns are reversal-like on average but become more continuation-like when accumulated through smoother past paths, using a survivorship-bias-mitigated sample.

AR-TF consequence: test path-continuity / jump-fraction features as interaction variables for momentum versus reversal rather than as standalone optimized indicators.

Reference: W. B. Kim, Price Path Continuity and the Cross-Section of Cryptocurrency Returns, 2026, SSRN 6871159.

### Risk-managed trend

Howden and Andreev (2026) study a fixed-lookback long/cash TSMOM sleeve with drawdown-state de-risking and describe the main result as drawdown control rather than alpha.

AR-TF consequence: drawdown de-risking is evaluated as a risk overlay and must be compared with the same strategy without the overlay; improvements in Calmar or tail risk do not automatically imply new alpha.

Reference: Howden & Andreev, Risk-Managed Time-Series Momentum in Crypto Majors, 2026, SSRN 7115459.

### Microstructure

Bieganowski and Slepaczuk (2026) report portable predictive structure across Binance Futures order-book and trade features, with order-flow imbalance, spread and adverse-selection effects, and distinguish maker and taker behavior under stress.

AR-TF consequence: microstructure strategies are a separate data track requiring point-in-time L2/L3/trade data, clock-quality evidence and fill simulation. They may not be approximated from daily bars.

Reference: Explainable Patterns in Cryptocurrency Microstructure, arXiv 2602.00776.

### Short-horizon mean reversion and the cost barrier

Kitron and Wengrowicz (2026) find pervasive 15-minute directional reversal but report gross edge near 1.3 bp per trade versus a 5 bp round-trip cost assumption.

AR-TF consequence: statistically detectable predictability below realistic friction is explicitly classified as NON_TRADABLE_SIGNAL, not edge.

Reference: Short-horizon mean reversion in cryptocurrency markets, arXiv 2608.21888.

### Variational latent factors

Boyer (2026) reports strong results for a crypto-adapted FactorVAE on 50 major cryptocurrencies, including high Sharpe for a momentum-filtered variant.

AR-TF consequence: FactorVAE is a deferred challenger. It must beat linear/tree factor baselines, survive PIT-universe reconstruction, transaction costs, multiple seeds, trial-count deflation and the same holdout policy before it receives any evidentiary weight.

Reference: Boyer, Cross-Sectional Return Prediction in Cryptocurrency Markets Using Variational Latent Factor Models, 2026, SSRN 6860920.

### Deep/RL skepticism requirement

Recent empirical comparisons continue to show that sophisticated models can fail to dominate simpler policies under realistic frictions. Deep hedging work on real BTC option data in 2026 found classical no-trade-band methods more cost-efficient than tested neural hedges, while reproducible RL comparisons emphasize identical execution assumptions and classical baselines.

AR-TF consequence: neural networks and reinforcement learning are challengers, not an escalation path. Complexity must earn admission through incremental economic value.

## Statistical anti-overfitting stack

Every family is counted in the research ledger. The final test stack is:

- common synchronous OOS timestamps;
- rolling and anchored walk-forward;
- purging and embargo where labels overlap;
- moving-block bootstrap;
- paired benchmark bootstrap;
- Deflated Sharpe Ratio using all registered attempts;
- CSCV Probability of Backtest Overfitting;
- White Reality Check on the full preregistered family;
- Hansen SPA as a complementary multiplicity test;
- parameter-plateau rejection of isolated optima;
- seed stability for stochastic models;
- feature ablation;
- regime, asset, year, liquidity and concentration decomposition;
- BASE / STRESSED / SEVERE costs;
- one untouched holdout after the winner is frozen.

White/Sullivan/Timmermann-style Reality Check is used because examining many trading rules creates data-snooping bias. Hansen SPA is complementary because the Reality Check can be conservative when the candidate set contains many poor models. DSR and PBO remain separate diagnostics: no single statistic is treated as sufficient evidence.

## Neural-network protocol

Neural candidates are trained only after dataset freeze. The following artifacts are mandatory for every run:

- dataset_sha256 and lifecycle_sha256;
- source code commit SHA;
- complete hyperparameter registry;
- deterministic data split identifiers;
- random seeds;
- feature timestamp audit;
- scaler/normalizer fitted on training only;
- training-log hash;
- model artifact hash;
- prediction artifact hash;
- parameter count and training compute;
- early-stopping source restricted to training/validation;
- no final-holdout use in architecture, feature or threshold selection.

Model ladder: ridge/elastic-net -> tree boosting -> LSTM/GRU/TCN -> iTransformer/TFT -> latent-factor/GNN -> RL. A later class is not tested merely because it is newer; it enters only when the preceding class has established a credible economic benchmark or a clear falsifiable limitation.

## Strategy mixture policy

Mixing old and new ideas is allowed only as preregistered structural ensembles. Components must first be evaluated separately. The ensemble must pass an incremental-value test against its strongest component. This prevents a large ensemble from hiding a weak component behind a favorable backtest.

Priority ensemble hypotheses:

1. TSMOM + volatility state + drawdown de-risking.
2. TSMOM/XSMOM + lagged dispersion scaling.
3. Momentum/reversal switch conditioned on price-path continuity and volatility.
4. Trend baseline + cost-aware gradient-boosting conviction gate.
5. PIT liquidity universe + volatility targeting + turnover budget.
6. Separate futures carry/basis sleeve only after funding and contract-lifecycle data are certified.
7. Separate microstructure execution alpha only after L2/L3/trade data are certified.

## Research stop rules

The process must stop or reject a family when:

- net expectancy is non-positive under BASE costs;
- STRESSED costs destroy the edge with no plausible capacity explanation;
- DSR < 0.95;
- PBO > 0.20;
- White RC / SPA does not support family-level superiority;
- parameter performance is an isolated spike;
- performance is concentrated in one coin, year or regime;
- the edge exists only under unavailable data or impossible fills;
- a complex model does not improve net economics over a simpler comparator;
- additional tuning would require looking at the final holdout.

A negative result is a valid research product. The preferred outcome is NO_EDGE_VERIFIED rather than a profitable-looking artifact created by repeated selection.
