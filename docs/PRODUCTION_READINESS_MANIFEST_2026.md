# Production Readiness Manifest 2026

## Purpose
The manifest is an evidence index and certification record, never an authorization token. Missing, stale, unverifiable, contradictory, scope-mismatched, or improperly bound cross-commit evidence is `NO_GO`. No AI/LLM output may independently authorize capital, modify risk limits, bypass reconciliation, or promote a strategy.

## Architectural invariant
`RESEARCH -> VERIFIED_BACKTEST -> PAPER -> TESTNET -> SHADOW -> LIVE_PILOT -> SCALED_LIVE`.
No stage may be skipped. Strategy selection and infrastructure certification are separate. The untouched final holdout remains closed during research/tournament selection.

## Mandatory scope binding
Every evidence set is bound to one explicit scope:

- `strategy_id`
- `asset_class`
- `venue`
- `market`
- `timeframe`
- `dataset_id`
- `environment`

The canonical scope payload receives a `scope_sha256`. Every PASS evidence item must carry that same digest. Evidence from a different strategy, venue, market, timeframe, dataset, or environment cannot certify the evaluated scope.

This is a hard isolation boundary. In particular, the certified AR-TF Binance Spot USDT/1D dataset cannot certify an external USDJPY/M15 runtime.

## Mandatory gate set
Every manifest contains exactly these gates and exactly one of `PASS`, `FAIL`, or `BLOCKED`; `ASSUMED_PASS` does not exist.

- G0 Repository Integrity
- G1 Data Integrity
- G2 Point-in-Time Universe
- G3 Dataset Freeze
- G4 Bias Audit
- G5 Strategy Preregistration
- G6 Backtest Correctness
- G7 OOS Validation
- G8 Statistical Validation
- G9 Cost Stress
- G10 Robustness
- G11 Regime Analysis
- G12 Liquidity/Capacity
- G13 Portfolio Construction
- G14 Risk Engine
- G15 Order Lifecycle
- G16 OMS/EMS
- G17 Exchange Adapter
- G18 Idempotency
- G19 Reconciliation
- G20 Security
- G21 Secrets/Identity
- G22 Supply Chain
- G23 CI/CD
- G24 Observability
- G25 Resilience
- G26 Backup/Restore
- G27 PAPER
- G28 TESTNET
- G29 SHADOW
- G30 LIVE_PILOT
- G31 Forward Evidence
- G32 Production Reconciliation

## Certification composition
A gate PASS alone is insufficient. The corresponding evidence domain must also contain immutable VERIFIED evidence with the expected scope identity and producer identity. This prevents a hand-written gate table from manufacturing readiness.

Same-commit evidence must be produced by the evaluated commit. Immutable evidence produced by an earlier/different commit is accepted only through an explicit producer/consumer binding that identifies the consumer commit, source run, source artifact, artifact digest, verification method, and successful external byte verification.

`DATA_VERIFIED` requires G1-G4 plus dataset evidence. `EDGE_VERIFIED` additionally requires G5-G13 plus quantitative evidence. `RISK_VERIFIED` requires G14 plus risk evidence. `EXECUTION_VERIFIED` requires G15-G18 plus execution evidence. `RECONCILIATION_VERIFIED` requires G19 and G32 plus reconciliation evidence. `SECURITY_VERIFIED` requires G20-G22 plus security, secrets/identity and supply-chain evidence. `PRODUCTION_INFRASTRUCTURE_VERIFIED` requires G0 and G23-G26 plus repository, CI/CD, observability, reliability, backup/restore, governance and FinOps evidence. TESTNET, SHADOW and LIVE_PILOT require their gates and operational evidence. `LIVE_PRODUCTION_READY_VERIFIED` requires every prerequisite certification and all G0-G32 PASS.

Even `LIVE_PRODUCTION_READY_VERIFIED` does not switch capital on: `paper`, `testnet`, `shadow`, `live_pilot`, and `scaled_live` authorizations remain separate explicit controls and live capital requires separate human authorization.

## Dataset acceptance contract
A dataset identity is accepted only from an externally verified P0-DATA-001 certificate when all are true:

- `decision = FROZEN_DATASET`
- `frozen = true`
- `unresolved_count = 0`
- `unresolved_anomaly_count = 0`
- `unresolved_gap_count = 0`
- `invalid_checksum_evidence_count = 0`
- `lifecycle_binding_verified = true`
- `source_plan_binding_verified = true`
- `holdout_evaluated = false`
- source artifact metadata, run identity, artifact digest, downloaded ZIP digest and certificate-file SHA-256 all verify
- `dataset_id` equals the manifest scope's dataset identity

The manifest distinguishes the certificate-file SHA-256 from the dataset content SHA-256 and records the producer commit separately from the evaluated consumer commit.

## Evidence domains
Repository, dataset, quantitative, execution, risk, reconciliation, security, secrets/identity, supply chain, CI/CD, observability, reliability, backup/restore, governance and FinOps are independent domains. A PASS item must name an immutable artifact, SHA-256, producer/source commit, issuer/certifier, expected scope digest and explicit `VERIFIED` result. Where provenance is required, attestation verification is mandatory.

## Quantitative evidence
Required evidence includes preregistered trial registry, common OOS folds, realistic fees/spread/slippage/impact, BASE/STRESSED/SEVERE scenarios, DSR, PBO, White Reality Check, Hansen SPA, bootstrap/permutation evidence, robustness plateau, regime analysis, capacity/liquidity, portfolio/risk results and the untouched final holdout. Infrastructure readiness cannot manufacture alpha. Failure yields `NO_EDGE_VERIFIED` / `NO_GO`.

The holdout cannot be used for strategy discovery, feature engineering, parameter tuning, model selection, regime selection, threshold adjustment, cost-model adjustment or retrying rejected candidates.

## Execution and risk evidence
The runtime architecture target is `Signal -> Portfolio -> Risk -> OrderIntent -> OMS -> EMS -> Exchange Adapter -> Reconciliation -> Evidence Ledger`. Required controls include durable OrderIntent before side effects, idempotency, UNKNOWN reconciliation, partial-fill/reject/cancel-replace semantics, exact venue/broker filters, fail-closed pretrade risk, kill switches, stale-data/desync protection, durable persistence and periodic/post-failure reconciliation. Any unresolved discrepancy disables trading.

Runtime logs are observability evidence, not authorization evidence. A runtime must additionally bind `commit_sha`, immutable build/release digest, strategy config digest, broker/venue identity, market/timeframe, data snapshot identity, environment and correlation/decision/order IDs. Ambiguous labels such as `approved=true` are forbidden when they could be mistaken for trade authorization; policy approval, model invocation and order authorization must be separate typed fields.

## 2026 supply-chain, agentic and operational controls
- SLSA v1.2 provenance model and consumer-side provenance verification.
- GitHub artifact attestations for releasable artifacts; provenance is not a security verdict and must be verified by consumers/policy.
- Sigstore/Cosign keyless OIDC signing for release artifacts where applicable; short-lived identity-bound certificates and transparency evidence.
- Full-length SHA-pinned GitHub Actions and dependency controls; SAST/SCA/secret/container/IaC scans; SBOM; vulnerability policy; immutable release digest.
- OpenTelemetry semantic conventions for traces, metrics and logs, with explicit trading/data/reconciliation SLI/SLOs and actionable alerts.
- NIST AI RMF and NIST AI 600-1 where probabilistic or agentic components participate; no critical authorization may depend exclusively on a model output.
- OWASP Agent Control Standard / agentic security controls where tools or agents can trigger external side effects: inspectability, traceability, runtime control, least privilege and fail-closed policy enforcement.
- Least privilege, workload identity, environment isolation, OpenBao/Vault-class secret management, policy-as-code and separate live credentials.
- Backup/PITR, restore drills, RPO/RTO, DR runbooks, chaos/load/soak and incident response evidence.

## CI and evidence-hash contract
The production-readiness workflow uses full-length SHA-pinned Actions, runs unit/contract tests, validates the generated manifest against JSON Schema Draft 2020-12, verifies externally sourced dataset bytes, asserts default-deny/NO_GO for incomplete evidence, and uploads the manifest artifact.

The generated file has a canonical SHA-256 that includes the generation timestamp. A separate `semantic_snapshot_sha256` excludes only `generated_at` and is reproducible for an otherwise identical evidence state. These identities must not be conflated.

## Authentic evidence currently connected
P0-DATA-001 / `ar-tf-v1d2-data` run #52 is the current externally verified data source for this manifest lineage:

- source commit: `801b3313616aa24bf033183a824ae60da639cae7`
- source run id: `34343007125`
- source artifact id: `10101457255`
- source artifact digest: `sha256:edc3cfdac868d33153733aa18aa98f39d08646ab345c8702883b379311660062`
- dataset SHA-256: `d1686e5fba9524c78e8a0e9a90d0f38efc1c6b883ebf1389dd4b47bb2984aaae`
- dataset freeze certificate file SHA-256: `72697eeeef2dbf03c732723c670666910325f5df5cfc499738c12b6803e863b3`
- scope: `AR-TF-v1 / CRYPTO_SPOT / BINANCE_SPOT / USDT_POINT_IN_TIME_UNIVERSE / 1D / ar-tf-binance-spot-usdt-1d-v1d2 / RESEARCH`

Production-readiness run #30 on consumer SHA `3533debf095b2854a2005f9f19e4811682ab6131` verified those external artifact bytes successfully and emitted a scope-bound manifest. Dataset evidence is PASS, but the manifest remains `decision=NO_GO`, `stage=RESEARCH`, `live_ready=false`, with all capital authorizations false because downstream gates are intentionally unfilled.

## Current quantitative blocker
The latest completed structural G4-G13 certificate before the Ridge compatibility rerun remains `NO_EDGE_VERIFIED`: G8 Statistical Validation, G10 Robustness and G11 Regime Analysis fail while the final holdout remains closed. The 407-trial preregistration must be executed according to its staged admission rules without relaxing thresholds. A Ridge compatibility fix for pandas 3 has been integrated on the quantitative research branch; its fresh evidence must be evaluated before any later stage is admitted.

Therefore the only institutionally valid current decision is `NO_GO` for live capital. Production engineering may continue, but production trading cannot be authorized until quantitative edge, operational forward evidence, reconciliation, security and explicit human promotion gates all pass for the exact same bound scope.
