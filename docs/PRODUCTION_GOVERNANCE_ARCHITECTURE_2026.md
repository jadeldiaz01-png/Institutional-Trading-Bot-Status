# Production Governance Architecture 2026

This increment adds a machine-readable control-plane contract without modifying the frozen AR-TF scientific variables.

## Safety boundary
The default decision is DENY. HOLDOUT stays CLOSED. Autonomous capital is zero. AI/agents/LLMs cannot authorize real orders, open the holdout, or promote PAPER/TESTNET/LIVE. Those transitions require deterministic evidence plus explicit human approval.

## Evidence-first architecture
Every promotion claim must bind repository identity, exact commit, workflow/run, artifact ID and SHA-256, dataset/config hashes, policy digest and timestamp. Code/config presence and a green workflow alone are not certification.

For Ridge CP03, the only admissible completion is the exact Cartesian inventory 27 trials x 12 folds = 324 checkpoints, with missing=0, duplicate=0, corrupt=0, lineage_mismatch=0, followed by 27/27 Ridge, total=149 and a digest-bound CP03-FINAL artifact. Any mismatch fails closed.

## Model lanes
Classical quant remains in RESEARCH. ML/DL use offline/shadow evaluation and cannot inherit authority from predictive metrics. LLM and multimodal systems are assistive: structured outputs, provenance, prompt-injection/tool-poisoning tests, capability allowlists and human approval for critical actions. RL remains simulation-only until an independently validated simulator and off-policy safety evidence exist.

## Runtime planes
Control: workload identity, policy, approvals, budgets, command/event buses and kill switches.
Data: point-in-time datasets/features, lineage, knowledge graph and append-only evidence.
Research: classical/ML/DL/LLM/multimodal experiments with preregistration and reproducibility.
Execution: durable OrderIntent, deterministic risk, OMS/EMS, adapters and reconciliation.
Agentic: registry, capability-scoped tools, sandbox, memory and model routing.
Observability: OpenTelemetry traces/metrics/logs plus domain audit events and SLO evaluation.
Supply chain: exact dependency/action pins, SBOM, SLSA provenance, Sigstore/GitHub attestations and verification before promotion.

## 2026 hardening
Use GitHub OIDC workload identity rather than long-lived CI secrets, with immutable OIDC subject claims where supported. Verify artifact attestations rather than merely generating them. Treat SLSA provenance as a digest-bound statement of how an artifact was produced. Standardize telemetry attributes with OpenTelemetry semantic conventions and pin the convention version used by dashboards and alerts.

## Operational gates
Risk/policy/identity/reconciliation failures block new risk. Runner interruption must resume from verified exact-lineage checkpoints. DR evidence includes backup/restore/PITR, dependency and policy outages, telemetry degradation and checkpoint recovery. FinOps enforces budgets and measures cost per verified experiment/checkpoint/correct agent outcome.

## General-income automation
Non-trading revenue agents may research, analyze, draft, score compliant leads, plan content and generate reports in a sandbox. Publication, external messaging, payments, contractual commitments and account changes require human approval. They receive no trading authority.

## Non-goals
This change does not claim EDGE_VERIFIED, does not authorize GBM, does not open HOLDOUT, and does not authorize PAPER, TESTNET, LIVE_PILOT or LIVE.
