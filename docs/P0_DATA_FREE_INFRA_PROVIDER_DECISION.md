# P0-DATA free infrastructure provider decision

Status: RESEARCH infrastructure decision only. This document does not certify production readiness.

## Decision
Use Oracle Cloud Always Free Ampere A1 as the preferred no-monthly-cost host for a single-node private k3s cluster running GitHub Actions Runner Controller (ARC) for the `p0-data-certifier` scale set.

## Why
- Oracle documents Always Free Ampere A1 compute capacity and persistent block storage suitable for a small research Kubernetes node.
- GitHub documents ARC as the recommended Kubernetes autoscaling solution and recommends ephemeral runners for autoscaling.
- Tailscale Personal may be used only for personal/non-commercial research access. It must not be treated as enterprise production networking evidence.

## Alternatives assessed
- Google Cloud Free Tier: useful for experimentation, but the always-free `e2-micro` instance is materially smaller for this dataset-certification workload. A free GKE control-plane allowance does not imply free worker compute sufficient for the workload.
- Local PC/homelab: zero provider cost and technically valid for research, but availability, power, network continuity, and external log retention are operator-dependent.
- ConoHa VPS: explicitly excluded by operator request.

## Security model
- No inbound public service is required for runner pods.
- ARC authenticates to GitHub using a GitHub App secret created out-of-band; never commit credentials.
- Runner scale set is `minRunners=0`, `maxRunners=1`.
- Runner jobs are ephemeral and must be externally logged before production claims.
- No broker credentials, exchange secrets, withdrawal permissions, or live trading capabilities are permitted.
- `LIVE_TRADING_ENABLED=false` remains invariant.

## Runtime gates before any certification
1. Oracle instance actually exists and is confirmed to remain within the chosen free allocation.
2. k3s node is Ready.
3. ARC controller and listener are healthy.
4. `p0-data-certifier` scale set is registered and idle with zero standing runners.
5. External logs are retained for controller, listener and runner.
6. A test job creates one runner and the runner is destroyed after the job.
7. `ar-tf-v1d2-data` is dispatched against the exact authorized SHA.
8. Artifact evidence proves `decision=FROZEN_DATASET`, `unresolved_count=0`, `unresolved_gap_count=0`, `invalid_checksum_evidence_count=0`, source checksums verified, and a coherent 64-character `dataset_sha256`.

Until every gate is evidenced, global decision remains `NO_GO` and `FROZEN_DATASET=false`.
