# Production Readiness Manifest 2026

## Purpose
The manifest is an evidence index and certification record, never an authorization token. Missing, stale, unverifiable, contradictory, or commit-mismatched evidence is `NO_GO`. No AI/LLM output may independently authorize capital, modify risk limits, bypass reconciliation, or promote a strategy.

## Architectural invariant
`RESEARCH -> VERIFIED_BACKTEST -> PAPER -> TESTNET -> SHADOW -> LIVE_PILOT -> SCALED_LIVE`.
No stage may be skipped. Strategy selection and infrastructure certification are separate. The untouched final holdout remains closed during research/tournament selection.

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
A gate PASS alone is insufficient. The corresponding evidence domain must also contain immutable, VERIFIED evidence bound to the evaluated commit SHA. This prevents a hand-written gate table from manufacturing readiness.

`DATA_VERIFIED` requires G1-G4 plus dataset evidence. `EDGE_VERIFIED` additionally requires G5-G13 plus quantitative evidence. `RISK_VERIFIED` requires G14 plus risk evidence. `EXECUTION_VERIFIED` requires G15-G18 plus execution evidence. `RECONCILIATION_VERIFIED` requires G19 and G32 plus reconciliation evidence. `SECURITY_VERIFIED` requires G20-G22 plus security, secrets/identity and supply-chain evidence. `PRODUCTION_INFRASTRUCTURE_VERIFIED` requires G0 and G23-G26 plus repository, CI/CD, observability, reliability, backup/restore, governance and FinOps evidence. TESTNET, SHADOW and LIVE_PILOT require their gates and operational evidence. `LIVE_PRODUCTION_READY_VERIFIED` requires every prerequisite certification and all G0-G32 PASS.

Even `LIVE_PRODUCTION_READY_VERIFIED` does not switch capital on: `paper`, `testnet`, `shadow`, `live_pilot`, and `scaled_live` authorizations remain separate explicit controls and live capital requires separate human authorization.

## Dataset acceptance contract
A dataset identity is accepted only from the authentic P0-DATA-001 certificate when all are true:

- `decision = FROZEN_DATASET`
- `frozen = true`
- `unresolved_count = 0`
- `unresolved_anomaly_count = 0`
- `unresolved_gap_count = 0`
- `invalid_checksum_evidence_count = 0`
- `lifecycle_binding_verified = true`
- `source_plan_binding_verified = true`
- `holdout_evaluated = false`

The manifest records `dataset_sha256`, `lifecycle_sha256`, dataset-manifest SHA, strategy version/config SHA, release artifact digest, test-report SHA, and quantitative/operational metrics when evidence exists. Missing identities remain explicit `null`; they are never invented.

## Evidence domains
Repository, dataset, quantitative, execution, risk, reconciliation, security, secrets/identity, supply chain, CI/CD, observability, reliability, backup/restore, governance and FinOps are independent domains. A PASS item must name an immutable artifact, SHA-256, source commit, issuer/certifier and explicit `VERIFIED` result. Where provenance is required, attestation verification is mandatory.

## Quantitative evidence
Required evidence includes preregistered trial registry, common OOS folds, realistic fees/spread/slippage/impact, BASE/STRESSED/SEVERE scenarios, DSR, PBO, White Reality Check, Hansen SPA, bootstrap/permutation evidence, robustness plateau, regime analysis, capacity/liquidity, portfolio/risk results and the untouched final holdout. Infrastructure readiness cannot manufacture alpha. Failure yields `NO_EDGE_VERIFIED` / `NO_GO`.

## Execution and risk evidence
The runtime architecture target is `Signal -> Portfolio -> Risk -> OrderIntent -> OMS -> EMS -> Exchange Adapter -> Reconciliation -> Evidence Ledger`. Required controls include durable OrderIntent before side effects, idempotency, UNKNOWN reconciliation, partial-fill/reject/cancel-replace semantics, exact exchange filters, fail-closed pretrade risk, kill switches, stale-data/desync protection, durable persistence and periodic/post-failure reconciliation. Any unresolved discrepancy disables trading.

## 2026 supply-chain and operational controls
- SLSA v1.2 provenance model.
- GitHub artifact attestations for releasable artifacts; provenance is not a security verdict and must be verified by consumers/policy.
- Sigstore/Cosign keyless OIDC signing for release artifacts where applicable; short-lived identity-bound certificates and transparency evidence.
- Pinned GitHub Actions and dependencies; SAST/SCA/secret/container scans; SBOM; vulnerability policy; immutable release digest.
- OpenTelemetry semantic conventions for traces, metrics and logs, with explicit trading/data/reconciliation SLI/SLOs and actionable alerts.
- NIST AI RMF and NIST AI 600-1 where probabilistic or agentic components participate; no critical authorization may depend exclusively on a model output.
- Least privilege, workload identity, environment isolation, OpenBao/Vault-class secret management, policy-as-code and separate live credentials.
- Backup/PITR, restore drills, RPO/RTO, DR runbooks, chaos/load/soak and incident response evidence.

## CI contract
The production-readiness workflow uses pinned actions, runs unit/contract tests, validates the generated manifest against JSON Schema Draft 2020-12, generates a deterministic canonical SHA-256, verifies that digest, asserts default-deny/NO_GO for incomplete evidence, and uploads the manifest artifact. Release signing/attestation belongs to the release path; routine test artifacts must not be mistaken for production provenance.

## Current dependency
PR #12 intentionally remains separate from PR #7. P0-DATA-001 must produce the definitive `FROZEN_DATASET` SHA first; only then should PR #12 be rebased onto that exact data branch state and consume the authentic certificate. Until then `DATA_VERIFIED=false`, `EDGE_VERIFIED=false`, `LIVE_PRODUCTION_READY_VERIFIED=false`, and `decision=NO_GO` are the only valid states.
