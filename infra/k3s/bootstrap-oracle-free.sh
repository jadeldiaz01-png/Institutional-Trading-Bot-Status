#!/usr/bin/env bash
set -euo pipefail

# Bootstrap a single-node k3s control plane for the P0-DATA certifier on an
# Oracle Cloud Always Free Ampere A1 VM (Ubuntu). Research-only until runtime
# evidence, logging, backup, and security gates are certified.
#
# Secrets MUST be provisioned out-of-band. This script deliberately does not
# accept GitHub, Tailscale, broker, or trading credentials.

if [[ ${EUID} -ne 0 ]]; then
  echo "run as root" >&2
  exit 1
fi

export INSTALL_K3S_EXEC="server --disable traefik --disable servicelb --write-kubeconfig-mode 0640"
curl -sfL https://get.k3s.io | sh -

systemctl enable --now k3s
kubectl wait --for=condition=Ready node --all --timeout=180s

kubectl create namespace arc-systems --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace arc-runners --dry-run=client -o yaml | kubectl apply -f -

cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: ResourceQuota
metadata:
  name: p0-data-runner-quota
  namespace: arc-runners
spec:
  hard:
    requests.cpu: "4"
    requests.memory: 8Gi
    limits.cpu: "4"
    limits.memory: 8Gi
    pods: "4"
---
apiVersion: v1
kind: LimitRange
metadata:
  name: p0-data-runner-limits
  namespace: arc-runners
spec:
  limits:
    - type: Container
      defaultRequest:
        cpu: "250m"
        memory: 256Mi
      default:
        cpu: "2"
        memory: 4Gi
EOF

cat <<'EOF'
K3S_BOOTSTRAP=PASS
NEXT_REQUIRED_EVIDENCE:
  - install Helm 3 from the official Helm release channel
  - install GitHub ARC controller in namespace arc-systems
  - create github-arc-app secret out-of-band (GitHub App preferred)
  - install infra/arc/values-p0-data.yaml as scale set p0-data-certifier
  - configure external log retention for ARC controller/listener/ephemeral runner
  - optionally install Tailscale for personal/non-commercial research access only
  - verify ephemeral runner is created for exactly one job and deleted afterward
  - dispatch ar-tf-v1d2-data with expected_sha equal to the exact authorized commit
EOF
