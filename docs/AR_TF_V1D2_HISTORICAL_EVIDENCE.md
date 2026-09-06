# AR-TF v1-D2 — Historical Evidence Acquisition

Status: **RESEARCH / NO_GO until a dataset freeze certificate proves otherwise**

## Objective

Build a reproducible, point-in-time Binance Spot USDT universe before any large-scale model tournament. The evidence layer must include assets that later disappeared or were delisted and must never reconstruct history from today's exchange state alone.

## Source hierarchy and claim-scoped authority

Evidence authority is scoped to the claim being made; a plausible URL or a single source is not a universal authorization token.

1. **Binance Vision public historical archives** — authoritative source for observed Binance market-data files, exact kline timestamps, ZIP checksums, and empirical gap boundaries.
2. **Binance official exchange announcements** — authoritative for Binance operational facts such as listing, delisting, trading suspension/reopening, pair changes, and exchange-performed migrations.
3. **Official token issuer/project material** — may establish an on-chain/token identity event such as a swap, fork, redenomination, contract migration, or denomination change. It may never by itself establish that Binance halted or resumed trading.
4. **Secondary contemporaneous sources** — corroboration and discovery only. They cannot independently change a gate to PASS.
5. **Current Spot API metadata** — diagnostic only; forbidden as the sole source for historical membership.

For a same-ticker redenomination supported by an official issuer source, the observed pre/post boundaries still come from checksum-verified Binance Vision data. The lifecycle is split into distinct economic episodes and no return may cross the identity event. No conversion ratio is applied to returns and no candles are manufactured.

## Gap-resolution policy

A gap has only three acceptable outcomes:

- `EXPECTED_NO_TRADING_INTERVAL`: requires authoritative Binance evidence for an exchange halt/reopening matching the observed interval.
- `SPLIT_LIFECYCLE_EPISODE`: requires an authoritative identity-break source (`BINANCE_OFFICIAL` or `TOKEN_ISSUER_OFFICIAL`) and produces distinct pre/post economic episodes.
- `DAILY_CHECKSUM_VERIFIED_*_RECOVERY`: every missing day must exist in official Binance Vision daily archives, pass its `.CHECKSUM`, contain exactly one expected 1d candle, and match the UTC day.

If any required daily archive is absent or invalid, recovery is atomic and no subset of rows is inserted. Unknown, contradictory, non-authoritative, or incompletely sourced events remain `UNRESOLVED` / `NO_GO`.

## Required evidence bundle

- `archive-observations.json`: every discovered Binance Vision `USDT/1d` monthly archive key and source URL.
- `lifecycle-candidates.json`: first/last archive month per symbol. These are candidates only.
- `provenance.json`: source method, retrieval time, SHA-256 of canonical observations and candidates, verification policy.
- `verified-lifecycle.csv`: lifecycle episodes with exact observed boundaries and evidence URLs.
- `lifecycle-verification-summary.json`: episode/symbol counts and lifecycle SHA-256.
- `internal-gap-repairs.json`: every attempted checksum-verified daily recovery, including failed attempts.
- `reconciliation-ledger.json`: deterministic duplicate/anomaly reconciliation.
- `gap-report.json`: observed, resolved, and unresolved calendar gaps.
- `checksum-report.json`: validation of monthly/daily source digests used by the dataset.
- `dataset-manifest.json`: immutable dataset/market/archive identities and source bindings.
- `dataset-freeze-certificate.json`: fail-closed certification result.

## Verified lifecycle contract

A historical download may only be unlocked when lifecycle ordering is valid, source policy is satisfied, required evidence is HTTPS/identifiable, every identity break is represented as a separate episode, no source archive is silently reused across incompatible economic identities, and every discovered historical symbol is either included or explicitly resolved/excluded with provenance.

## Important distinction

Archive presence proves that Binance Vision contains data for that symbol/month. Archive absence does **not** by itself prove delisting. Maintenance, data gaps, symbol migrations, redenominations, pair removals, or archive coverage differences can produce boundaries that require corroboration.

Therefore v1-D2 separates:

`DISCOVERY -> BOUNDARY_CANDIDATE -> CORROBORATED -> VERIFIED_LIFECYCLE -> DATASET_BUILD -> RECONCILIATION -> GAP/CHECKSUM AUDIT -> FROZEN_DATASET`

No downstream tournament may accept a dataset identity unless the authentic certificate simultaneously proves:

- `decision == FROZEN_DATASET`
- `frozen == true`
- `unresolved_count == 0`
- `unresolved_gap_count == 0`
- `unresolved_anomaly_count == 0`
- `invalid_checksum_evidence_count == 0`
- `lifecycle_binding_verified == true`
- `source_plan_binding_verified == true`
- `holdout_evaluated == false`

## Survivorship-bias policy

- Never start from the current `exchangeInfo` symbol list and backfill prices.
- Include delisted/dead symbols when historical evidence exists.
- Preserve symbol lifecycle at each timestamp.
- Universe ranking uses only information known before the rebalance timestamp.
- Missing or ambiguous lifecycle evidence fails closed.

## Reproducibility

The discovery bundle is canonicalized and SHA-256 hashed. The dataset manifest binds the verified lifecycle, source plan, market CSVs, archive manifests, reconciliation ledger, gap report, checksum report, and recovery ledgers. Every tournament record must bind to the final certified dataset SHA, lifecycle SHA, code SHA, strategy/configuration hash, and fold definition.

## Promotion rule

v1-D2 can produce `FROZEN_DATASET` only for the research data layer. It cannot authorize PAPER, TESTNET, SHADOW, LIVE_PILOT, or LIVE. After a genuine freeze, the next permitted operation is binding the preregistered research tournament to that immutable dataset while the final holdout remains closed.
