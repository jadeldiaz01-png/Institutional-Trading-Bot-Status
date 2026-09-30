# M0→M7 Edge Lab

Research-only framework for measuring whether incremental information sets add **net out-of-sample edge**.

## Safety boundary

This lab is isolated from the frozen CP03 scientific lineage.

- `LIVE_TRADING_ENABLED=false`
- no order placement
- no exchange credentials
- no withdrawals
- no leverage changes
- no access to the existing CP03 untouched holdout
- no automatic promotion to PAPER, TESTNET, LIVE_PILOT or LIMITED_LIVE
- `EDGE_VERIFIED` is never set by this framework

The output can only label a model as a **research candidate**. A later human-governed certification must decide whether any candidate deserves a new, independently frozen holdout.

## Ablation ladder

| Model | Incremental information set |
|---|---|
| M0 | multi-horizon momentum |
| M1 | M0 + cross-crypto lead/lag |
| M2 | M1 + derivatives pressure: funding, OI, basis, taker imbalance |
| M3 | M2 + order-flow / book microstructure |
| M4 | M3 + on-chain activity |
| M5 | M4 + conventional news/sentiment features |
| M6 | M5 + structured LLM event features |
| M7 | M6 + regime features / full ensemble |

Every model is evaluated on the same chronological walk-forward slices, cost model and benchmark.

## Public data adapters

`src/edge_lab/providers.py` contains read-only adapters for:

- Binance Spot public klines;
- Binance COIN-M public funding history, open-interest history, taker buy/sell volume, basis and book ticker;
- Coin Metrics Community API asset metrics.

The adapters only issue HTTP GET requests to an allowlist of public market-data hosts. They have no signing code and no order endpoints.

### Important retention constraint

Several Binance derivatives statistics endpoints expose only recent history. Persist raw responses with timestamps and hashes if these features are to be evaluated over longer windows. Do not backfill missing history with synthetic observations and label it real.

## Required feature table

The ablation runner consumes a point-in-time CSV. Each row represents information known at decision time and must include:

- `timestamp`
- `forward_return` — return strictly after the decision timestamp
- `benchmark_return`
- optional `funding_bps`
- optional `spread_bps`
- feature columns defined in `protocol.json`

Missing features do not silently become evidence. A model with no usable features for a row stays flat.

## Run

```bash
PYTHONPATH=src python3 scripts/run_m0_m7_ablation.py \
  --input path/to/point_in_time_features.csv \
  --output m0_m7_result.json
```

## Interpretation

The report includes gross return, net return, benchmark return, simple alpha, Sharpe, max drawdown, turnover, cost drag and positive OOS fold counts.

`candidate_screen_pass=true` is **not** an edge certification. It only means the result passed the deliberately modest research screen encoded in the protocol. Multiple-testing correction, independent holdout evaluation, capacity analysis, robustness by regime, Deflated/Probabilistic Sharpe and shadow execution evidence remain separate gates.
