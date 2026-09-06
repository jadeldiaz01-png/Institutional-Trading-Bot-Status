# P0-DATA private ephemeral runner runbook

Status: infrastructure scaffold only. This document does not certify a runtime, dataset, strategy, paper, testnet, or live environment.

## Purpose

Provide an isolated Kubernetes execution substrate for `ar-tf-v1d2-data` using GitHub Actions Runner Controller (ARC) ephemeral runners. Tailscale Personal may be used only for personal/non-commercial research access. It must not be represented as the production enterprise network tier.

## Invariants

- `LIVE_TRADING_ENABLED=false`.
- No exchange credentials, broker credentials, withdrawal permissions, trading keys, or production secrets are required.
- Dataset certification must fail closed unless the exact dispatched SHA matches `expected_sha`.
- ARC runners are ephemeral and process one job before removal.
- Runner logs must be exported to durable external storage before production classification.
- Kubernetes API must not be publicly exposed solely for CI convenience.
- Do not store GitHub App private keys or Tailscale OAuth secrets in Git.

## Recommended topology

Internet -> GitHub Actions service -> ARC listener -> ephemeral runner pod

Operator access -> Tailscale -> private Kubernetes API

Runner egress -> GitHub + Binance Vision HTTPS

There is no inbound path from the public Internet to a runner pod.

## Kubernetes

For zero additional software-license cost, use an existing Linux host and a conformant Kubernetes distribution such as k3s/kubeadm. A local `kind` cluster is suitable only for development, not certification evidence intended to represent a persistent institutional runtime.

Create the guardrails first:

```bash
kubectl apply -f infra/arc/p0-data-runner-guardrails.yaml
```

## GitHub ARC

Install the official controller with Helm and pin a reviewed chart version before certification:

```bash
helm install arc \
  --namespace arc-systems \
  --create-namespace \
  oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set-controller
```

Use a GitHub App or other least-privilege GitHub-supported ARC credential. Do not commit credentials. Create the Kubernetes Secret out-of-band and verify its namespace and RBAC before deploying the scale set.

Then install the runner scale set using:

```bash
helm install p0-data-certifier \
  --namespace arc-runners \
  --create-namespace \
  -f infra/arc/values-p0-data.yaml \
  oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set
```

The workflow label is `p0-data-certifier`.

## Tailscale research access

Tailscale Personal is free but restricted by Tailscale to personal/non-commercial use. It can secure operator access during personal research, but it is not an enterprise production certification dependency.

Prefer workload identity federation where available. If OAuth is used, create the credentials outside Git, grant only the scopes and tags required by the Tailscale Kubernetes Operator, and store them as Kubernetes Secrets or in an external secret manager.

Do not paste OAuth client secrets into this repository.

## Pre-dispatch evidence gate

Before running `ar-tf-v1d2-data`, collect and preserve:

1. Kubernetes cluster version and node OS/kernel.
2. ARC controller/chart version and image digest.
3. Runner image digest/version.
4. Namespace Pod Security admission state.
5. RBAC bindings for the runner ServiceAccount.
6. Proof that runner scale set `p0-data-certifier` is healthy.
7. Proof that `minRunners=0`, `maxRunners=1` is effective.
8. Proof that a runner is created for a job and removed afterward.
9. Durable ARC/controller/listener/runner logs.
10. Exact Git commit SHA to pass as `expected_sha`.

Any missing item is `NO_GO` for infrastructure certification.

## Dataset certification gate

The execution is successful only when the workflow artifact proves all of the following:

```text
decision = FROZEN_DATASET
frozen = true
unresolved_count = 0
unresolved_anomaly_count = 0
unresolved_gap_count = 0
invalid_checksum_evidence_count = 0
all_source_checksums_verified = true
dataset_sha256 = 64 hexadecimal characters
holdout_evaluated = false
paper_authorized = false
testnet_authorized = false
live_authorized = false
```

The SHA in the certificate must equal the exact authorized workflow SHA. A successful runner or green infrastructure test is not dataset certification.

## Production classification

This implementation remains `RESEARCH/IMPLEMENTING` until runtime evidence exists. Tailscale Personal cannot be used as evidence of enterprise/commercial production readiness under its stated plan terms. Production classification also requires pinned supply-chain artifacts, centralized immutable logs, restore/DR evidence, vulnerability/SBOM/provenance gates, secret-manager integration, SLOs, alerting, incident runbooks, and explicit human approval.
