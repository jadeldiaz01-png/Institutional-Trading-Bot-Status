# Private Certification Infrastructure 2026

Status: **CONTRACT_IMPLEMENTED / RUNTIME_BLOCKED_EXTERNAL until real cluster evidence exists**

## Objective

Provide a low-cost, fail-closed certification plane for institutional evidence using:

- Tailscale Personal for private connectivity.
- GitHub Actions Runner Controller (ARC) for ephemeral/JIT-style single-job runners.
- A private Kubernetes cluster whose control plane is not exposed to the public internet.
- Runtime evidence bound to an exact Git commit SHA.

This infrastructure cannot authorize PAPER, TESTNET, SHADOW, LIVE_PILOT, or LIVE by itself.

## Cost boundary

Tailscale Personal and GitHub self-hosted runners do not add a software-license charge for this design. Kubernetes compute is **not inherently free**; zero incremental compute cost requires an existing VPS/server/local machine. FinOps must treat any VPS/cloud usage as infrastructure cost even when the software is free.

The design uses `minRunners: 0` and `maxRunners: 1` to avoid idle runner cost and bound concurrency. Tailscale ephemeral-resource quota must be monitored; exceeding plan limits is a `BLOCKED_EXTERNAL/CAPACITY` event, never a reason to weaken controls.

## Architecture

```text
GitHub Actions control plane
        |
        | outbound HTTPS only
        v
ARC listener/controller (separate namespace)
        |
        v
trading-certifier-jit runner pod (arc-runners)
        +-- GitHub runner container, one job
        +-- Tailscale userspace sidecar, ephemeral identity
        |
        +--> private .ts.net probe / tailnet-only evidence endpoint
        |
        +--> repository checkout at exact expected SHA
```

The Kubernetes API server should be reachable administratively only over a private network/tailnet. Do not enable Tailscale Funnel for the certifier plane.

## Required Kubernetes namespaces

- `arc-systems`: ARC controller/listener.
- `arc-runners`: ephemeral runner pods only.
- `tailscale`: Tailscale Kubernetes Operator if used for private API-server access or shared ingress/egress.

GitHub recommends separating runner pods from controller pods. Production workloads must not share the certification runner namespace.

## Secrets

Never commit:

- GitHub PATs.
- GitHub App private keys.
- Tailscale auth/OAuth keys.
- kubeconfigs.
- exchange API keys.
- OpenBao root/static tokens.

Required secret references:

- `arc-runners/trading-certifier-github-app`: GitHub App authentication for ARC.
- `arc-runners/tailscale-ephemeral`: `TS_AUTHKEY` created as ephemeral, pre-authorized, and scoped to `tag:ci-certifier`.

Prefer GitHub App over PAT for ARC. Prefer Tailscale workload identity federation where a supported identity provider is available; otherwise use the narrowly scoped ephemeral key and rotate it.

## Network policy

`kubernetes-isolation.yaml` applies namespace Pod Security `restricted`, default-deny ingress/egress, DNS, and TCP/443 egress only. Production deployment must add destination allowlisting at CNI/firewall level for GitHub, GHCR, Tailscale control/DERP, and explicitly approved evidence endpoints.

The runner accepts no inbound connection. The Tailscale sidecar uses userspace networking and therefore requires neither `NET_ADMIN` nor `/dev/net/tun`.

## ARC runner contract

`arc-runner-values.yaml` requires:

- `runnerScaleSetName: trading-certifier-jit`
- `minRunners: 0`
- `maxRunners: 1`
- no Kubernetes service-account token in the runner pod
- one ephemeral runner identity per job
- Tailscale state stored only in `emptyDir`
- no long-lived credential in repository content

ARC must be installed from a pinned Helm chart version/digest during real provisioning. The exact controller/chart/image digests must be captured in the runtime certificate before G22/G23 can PASS.

## Runtime certification

`.github/workflows/private-certifier-runtime.yml` is manual only. It requires:

1. exact `expected_sha == GITHUB_SHA`;
2. runner reports `CI_RUNNER_EPHEMERAL=true`;
3. Kubernetes pod/namespace/node identity is present;
4. namespace is exactly `arc-runners`;
5. a real private `.ts.net` health endpoint succeeds through the local Tailscale SOCKS5 sidecar;
6. the evidence artifact is SHA-256 hashed;
7. every trading authorization remains false.

A green ordinary GitHub-hosted workflow is insufficient. The runtime evidence must come from `runs-on: trading-certifier-jit`.

## Evidence required before infrastructure gates can pass

The runtime bundle must eventually include:

- GitHub run ID and attempt.
- exact commit SHA.
- runner name/OS/architecture.
- Kubernetes pod, namespace, node UID/name.
- Kubernetes server version.
- ARC controller chart version and image digest.
- runner image digest/version.
- proof of one-job ephemeral deregistration after job completion.
- Tailscale node identity/tag and successful private probe.
- Tailscale plan/quota state at execution time.
- NetworkPolicy and Pod Security admission evidence.
- external log retention location and digest.
- SBOM/provenance/signature for any custom runner image.

Until these are real, the manifest must keep G20-G26 at BLOCKED/PARTIAL as appropriate.

## Minimal human/external actions

1. Provide an existing machine/VPS/local host for the private Kubernetes cluster, or explicitly approve a compute provider/cost.
2. Create/choose the Tailscale Personal tailnet and `tag:ci-certifier` policy.
3. Create the narrowly scoped ephemeral Tailscale credential (or workload identity trust).
4. Create a GitHub App for ARC with the minimum runner-management permissions and install it on this repository.
5. Put both credentials into Kubernetes Secrets, never into GitHub source.
6. Install a pinned Kubernetes distribution, ARC chart, and optionally the Tailscale Kubernetes Operator for private kube-apiserver access.
7. Provide a private `.ts.net` `/healthz` probe reachable only through the tailnet.
8. Trigger `private-certifier-runtime` with the exact commit SHA.

If any required credential, runner, cluster, private probe, or log sink is unavailable, state is `BLOCKED_EXTERNAL`; do not substitute synthetic evidence.
