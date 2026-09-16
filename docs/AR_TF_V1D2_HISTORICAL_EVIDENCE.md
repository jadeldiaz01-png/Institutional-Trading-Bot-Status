# AR-TF v1-D2 — Historical Evidence Acquisition

Status: **RESEARCH / NO_GO**

## Objective

Build a reproducible, point-in-time Binance Spot USDT universe before any large-scale model tournament. The evidence layer must include assets that later disappeared or were delisted and must never reconstruct history from today's exchange state alone.

## Source hierarchy

1. Binance Vision public historical archives: discovery of symbol/month presence and immutable market-data boundaries.
2. Binance official listing/delisting announcements when available: corroboration of effective trading boundaries.
3. Historical kline first/last timestamps: market-data boundary evidence, not automatically an announcement-equivalent lifecycle timestamp.
4. Current Spot API metadata: diagnostic only; forbidden as the sole source for historical membership.

## Required evidence bundle

- `archive-observations.json`: every discovered Binance Vision `USDT/1d` monthly archive key and source URL.
- `lifecycle-candidates.json`: first/last archive month per symbol. These are candidates only.
- `provenance.json`: source method, retrieval time, SHA-256 of canonical observations and candidates, verification policy.
- `verified-lifecycle.csv`: curated lifecycle table with exact timestamps and evidence URLs.
- `evidence-readiness.json`: fail-closed gate that is `NO_GO` until every required lifecycle boundary is verified.

## Verified lifecycle contract

Columns:

- `symbol`
- `listed_at`
- `delisted_at` (blank if still active at the dataset cutoff)
- `listing_evidence_url`
- `delisting_evidence_url`
- `listing_status`
- `delisting_status`

A historical download may only be unlocked when listing boundaries are `VERIFIED`, all actual delisting boundaries are `VERIFIED`, evidence URLs are HTTPS, and lifecycle ordering is valid.

## Important distinction

Archive presence proves that Binance Vision contains data for that symbol/month. Archive absence does **not** by itself prove delisting. Maintenance, data gaps, symbol migrations, redenominations, pair removals, or archive coverage differences can produce boundaries that require corroboration.

Therefore v1-D2 separates:

`DISCOVERY -> BOUNDARY_CANDIDATE -> CORROBORATED -> VERIFIED -> HISTORICAL_DOWNLOAD_READY`

Only `HISTORICAL_DOWNLOAD_READY` may feed the v1-D tournament dataset builder. It still does not authorize PAPER.

## Survivorship-bias policy

- Never start from the current `exchangeInfo` symbol list and backfill prices.
- Include delisted/dead symbols when historical evidence exists.
- Preserve symbol lifecycle at each timestamp.
- Universe ranking uses only information known before the rebalance timestamp.
- Missing or ambiguous lifecycle evidence fails closed.

## Reproducibility

The discovery bundle is canonicalized and SHA-256 hashed. The eventual dataset manifest must additionally hash the verified lifecycle file and downloaded market data. Every tournament record must bind to dataset SHA, lifecycle SHA, code SHA, configuration hash, and fold definition.

## Promotion rule

v1-D2 can produce only `HISTORICAL_DOWNLOAD_READY`. It cannot produce `PAPER_CANDIDATE`, PAPER, TESTNET, or LIVE authorization.
