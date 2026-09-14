# Web 4.0 AI Integration 2026

Status: **RESEARCH / ADVISORY ONLY / NO TRADING AUTHORITY**

## Definition used here

"Web 4.0" is not treated as a formal standards generation or a profitability factor. In this repository it is shorthand for an agentic, semantic, identity-aware and distributed web stack composed only of technologies with individually testable value.

## 2026 evidence review

### MCP 2026-07-28 — ADVISORY_ADMITTED
The July 2026 MCP specification introduced a stateless protocol core, HTTP-header routing, cacheable list results, Tasks/extensions and authorization hardening. It is the preferred agent-to-tool boundary. Sensitive operations still require policy and approval; MCP does not grant execution authority.

### A2A v1.0 — ADVISORY_ADMITTED
A2A v1.0 reached stable production-ready status in March 2026 and complements MCP: MCP is agent-to-tool/context while A2A is agent-to-agent. In this system A2A is limited to research delegation and evidence exchange.

### W3C DID 1.1 + Verifiable Credentials — RESEARCH_ONLY
DID 1.1 reached Candidate Standard in March 2026, while W3C continued work on Digital Credentials and threat models. It is promising for portable agent identity and signed attestations but does not replace OpenBao/OIDC/SPIFFE-style workload identity. Revocation, issuer trust, privacy and correlation risks must be evaluated first.

### Knowledge Graph RAG — RESEARCH_ONLY
2026 graph/LLM research shows structured retrieval can improve grounding and reasoning in knowledge-intensive systems. For trading research, the useful target is not price prediction by LLM. It is provenance-aware retrieval over the Evidence Ledger, experiment registry, strategy hypotheses, dataset hashes and contradictions.

### Confidential AI / TEE — EVALUATE_ONLY
Confidential computing protects data while in use and can strengthen isolation for credentials, proprietary research or private model inference. It is not automatically justified for public OHLCV processing. Admission requires measured security benefit versus latency and infrastructure cost.

## Quantitative admission model

Each component receives a 0-100 score:

- maturity: 20%
- security: 25%
- evidence quality: 20%
- trading/research relevance: 25%
- operational simplicity: 10%

Minimum automatic advisory admission: **70/100**. Experimental technologies remain `RESEARCH_ONLY` regardless of score until their own evaluation is complete.

This score is an engineering admission prior, **not a claim of alpha or profitability**.

## Runtime boundaries

Allowed AI/Web4 capabilities are research-only: retrieve evidence, query verified knowledge, summarize research, propose hypotheses, run sandbox evaluations and emit signed evidence.

Explicitly denied: order placement/cancellation, changes to risk limits, opening the frozen holdout, strategy promotion, enabling live trading, moving capital or writing exchange credentials.

The execution path remains deterministic:

`Research/AI -> Evidence -> Portfolio hypothesis -> Risk Engine -> Policy -> OrderIntent -> OMS -> Adapter -> Exchange -> Reconciliation`

AI stops before Risk/Policy/OMS authority.

## Required quantitative evaluation

Before expanding any component, measure at minimum: p50/p95 latency, error rate, availability, compute/token cost, security findings, evidence-grounding accuracy, unsupported-claim rate and human override rate. For KG-RAG, evaluate claim precision/recall and citation correctness on a frozen benchmark. For A2A/MCP, run fault injection for timeouts, malformed responses, duplicate tasks, identity failures and privilege-escalation attempts.

## Research roadmap

P0: MCP read-only research tools + signed Evidence Ledger bindings.

P1: KG-RAG over immutable experiment/evidence artifacts with deterministic citation verification.

P2: A2A research delegation between isolated research agents with deny-by-default Agent Cards and capability scopes.

P3: DID/VC pilot for agent attestations only if it demonstrates value beyond existing workload identity.

P4: confidential inference only for workloads containing secrets/private intellectual property where threat-model and latency/cost measurements justify it.

No Web4 component can advance PAPER, TESTNET or LIVE status on its own.
