# Production Readiness Manifest 2026

## Purpose
This manifest is an evidence index, not an authorization token. It is fail-closed: missing, stale, unverifiable, or contradictory evidence is `NO_GO`. No AI/LLM output can independently authorize capital, change risk limits, or promote a strategy.

## Architectural invariant
`RESEARCH -> VERIFIED_BACKTEST -> PAPER -> TESTNET -> SHADOW -> LIVE_PILOT -> SCALED_LIVE`.
No stage may be skipped. Promotion requires objective evidence plus the applicable human approval. The untouched holdout remains physically/logically excluded until the preregistered tournament produces at most `FROZEN_HOLDOUT_CANDIDATE`.

## Evidence domains
1. **Dataset**: point-in-time universe; lifecycle episodes; checksums; gap report; deterministic reconciliation ledger; immutable `dataset_sha256`; source-plan and code SHA; zero unresolved defects.
2. **Quantitative**: preregistered trial registry; common folds; OOS; CPCV/PBO; DSR; block bootstrap; White Reality Check/SPA; benchmark superiority; regime/cost/capacity/parameter-plateau evidence; untouched final holdout.
3. **Execution**: durable OrderIntent; idempotency; UNKNOWN state; reconciliation; OCO/cancel-replace; filters/rounding/min-notional; partial fills/rejects; latency/slippage/impact; exchange execution reports.
4. **Risk**: independent fail-closed pretrade Risk Engine; exposure/leverage/concentration/liquidity/drawdown limits; kill switches; stale-data and reconciliation circuit breakers; dual approval for high-risk changes.
5. **Security**: least privilege; workload identity; OpenBao; OPA/Rego; environment isolation; egress allowlists; secret scanning; SAST/SCA; threat model; prompt/tool injection controls for agentic components.
6. **Supply chain**: pinned actions/dependencies; SBOM; signed immutable artifacts; build provenance/attestations; dependency review; vulnerability policy; reproducible release metadata.
7. **Reliability**: idempotent workers; bounded retries/backoff/jitter; durable queues; PostgreSQL HA/PITR; restore drills; DR/RTO/RPO; chaos/load/soak; runbooks; capacity limits.
8. **Observability**: OpenTelemetry traces/metrics/logs; stable semantic conventions; SLI/SLO/error budgets; trading/data/reconciliation SLOs; actionable alerts and incident correlation.
9. **Governance**: separation of duties; immutable audit/evidence ledger; approvals; model/data cards; retention/classification; incident response; change control; agent/tool allowlists; autonomy boundaries.
10. **FinOps**: budgets and quotas for compute/storage/network/API/model tokens; cost attribution per research run; capacity forecasts; hard spend ceilings; cost-per-correct-result reporting.

## 2026 external controls incorporated
- GitHub OIDC for short-lived cloud identity; no long-lived deployment secrets.
- GitHub artifact attestations/Sigstore provenance and SBOM verification for release artifacts; attestations are provenance, not a security verdict.
- OpenSSF Scorecard/dependency evaluation as supply-chain inputs.
- OpenTelemetry semantic conventions for interoperable telemetry.
- NIST AI RMF/GenAI profile and adversarial ML taxonomy for AI governance/evaluation.
- OWASP Agentic Security Initiative/Top 10 controls for agent tools, MCP/skills, privilege boundaries and prompt/tool injection.
- Binance Spot API semantics: ambiguous/UNKNOWN execution must reconcile against authoritative order/account state; account/symbol filters and rate limits are runtime constraints.

## Revenue objective
Revenue is an outcome, never a gate override. For trading, `edge` means statistically robust positive net expectancy after realistic costs and stress, then forward evidence through PAPER/TESTNET/SHADOW before any live pilot. Infrastructure readiness cannot manufacture alpha. If the evidence does not pass, the correct production decision is `NO_GO` / `NO EDGE VERIFIED`.

## Required signed artifacts before any production claim
`production-readiness-manifest.json`, manifest SHA-256, dataset freeze certificate, quantitative certification report, execution certification report, risk-policy bundle, SBOM, build provenance/attestation, vulnerability report, DR/restore evidence, SLO report, governance approval record, FinOps budget/capacity report.
