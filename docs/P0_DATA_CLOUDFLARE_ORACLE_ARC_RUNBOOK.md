# P0-DATA-001 — Cloudflare + Oracle/k3s/ARC runbook

## Objective
Provide private administrative access, off-runner evidence retention, and ephemeral execution for the P0-DATA-001 dataset certifier without changing any quantitative authorization gate.

## Architecture
- Oracle Cloud Always Free Ampere A1: single-node k3s research runtime.
- GitHub Actions Runner Controller: `p0-data-certifier` ephemeral scale set (`minRunners=0`, `maxRunners=1`).
- Cloudflare Tunnel: outbound-only connectivity from k3s. No Kubernetes API public exposure is required.
- Cloudflare Zero Trust: operator access policy in front of private administrative routes.
- Cloudflare R2 Standard: private evidence/log retention target.

## Security invariants
- Never commit Cloudflare tunnel tokens, R2 access keys, GitHub App keys, PATs, kubeconfig, exchange keys, or trading credentials.
- Create Kubernetes Secrets out-of-band from a trusted terminal or secret manager.
- Scope the R2 token to Object Read & Write on one dedicated evidence bucket only.
- Keep `LIVE_TRADING_ENABLED=false` and all PAPER/TESTNET/LIVE authorization flags false.
- Infrastructure success is not dataset certification.
- The runner cluster is dedicated to CI/research; do not colocate production workloads.

## 1. Bootstrap k3s
Run the repository bootstrap on the provisioned Oracle A1 host, then verify node readiness.

## 2. Install ARC
Install the official ARC controller in `arc-systems`; install the runner scale set from `infra/arc/values-p0-data.yaml` in `arc-runners`.
Authentication material must be injected as a Kubernetes Secret and never stored in Git.

## 3. Configure Cloudflare Tunnel
Create a remotely managed tunnel in Cloudflare. Create its Kubernetes Secret without writing the token to a checked-in file:

```bash
kubectl create namespace cloudflare-system --dry-run=client -o yaml | kubectl apply -f -
kubectl -n cloudflare-system create secret generic cloudflared-tunnel-token \
  --from-literal=token="$CLOUDFLARE_TUNNEL_TOKEN"
kubectl apply -f infra/cloudflare/cloudflared-deployment.yaml
kubectl -n cloudflare-system rollout status deploy/cloudflared
```

Use Cloudflare Zero Trust policies to require authenticated operator identity. Do not make the Kubernetes API anonymously/publicly reachable.

## 4. Configure R2 evidence bucket
Create one private Standard bucket, e.g. `institutional-trading-bot-evidence`. Create an R2 S3 credential restricted to that bucket only.
Runtime variables:

```text
R2_ACCOUNT_ID
R2_BUCKET
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_REGION=auto
```

Never print their values. R2 endpoint format:
`https://<ACCOUNT_ID>.r2.cloudflarestorage.com`.

## 5. Pre-dispatch gate

```bash
bash infra/arc/verify-p0-data-runtime.sh
```

Required decision: `ARC_RUNTIME_PRE_DISPATCH_READY` and standing runners = 0.

## 6. Observe ephemeral lifecycle
Start in a separate terminal:

```bash
bash infra/arc/observe-ephemeral-runner.sh
```

Required lifecycle: 0 -> >=1 -> 0. Preserve controller/listener/runner logs externally.

## 7. Dispatch exact SHA
Before dispatch, resolve the current PR head SHA. Dispatch `ar-tf-v1d2-data` with:
- agent=`dataset-certifier`
- environment=`research`
- expected_sha=`<exact current authorized SHA>`

Never reuse a stale SHA from documentation.

## 8. Dataset gate
The workflow must prove all of:
- `decision == FROZEN_DATASET`
- `frozen == true`
- `unresolved_count == 0`
- `unresolved_anomaly_count == 0`
- `unresolved_gap_count == 0`
- `invalid_checksum_evidence_count == 0`
- `all_source_checksums_verified == true`
- manifest and certificate `dataset_sha256` match and are 64 hex chars
- certificate `code_sha` equals the exact authorized SHA
- holdout not evaluated
- PAPER/TESTNET/LIVE remain unauthorized

Anything else is `NO_GO`.

## 9. Retain evidence in R2
After successful artifact creation, from a trusted environment with temporary/restricted R2 credentials:

```bash
chmod +x infra/cloudflare/upload-evidence-r2.sh
infra/cloudflare/upload-evidence-r2.sh artifacts/ar_tf_v1d2_dataset
```

The uploader creates `SHA256SUMS` and writes under:
`p0-data-001/<code_sha>/<run_id>/`.

R2 retention strengthens durability but is not by itself proof of immutability. Production certification should add signed provenance/evidence ledger and retention governance.

## Failure policy
Any failed identity, tunnel, ARC, runner lifecycle, checksum, dataset, or evidence-retention check leaves P0-DATA-001 in progress and global state `NO_GO`.
