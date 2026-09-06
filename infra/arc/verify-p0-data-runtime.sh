#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-artifacts/p0_data_runtime}"
mkdir -p "$OUT_DIR"

fail() {
  printf 'P0-DATA runtime verification failed: %s\n' "$*" >&2
  exit 1
}

command -v kubectl >/dev/null 2>&1 || fail "kubectl not found"

NODE_JSON="$OUT_DIR/nodes.json"
ARC_SYSTEMS_JSON="$OUT_DIR/arc-systems-pods.json"
ARC_RUNNERS_JSON="$OUT_DIR/arc-runners-pods.json"
ARC_RESOURCES_TXT="$OUT_DIR/arc-resources.txt"
SUMMARY_JSON="$OUT_DIR/runtime-verification.json"

kubectl get nodes -o json > "$NODE_JSON"
kubectl get pods -n arc-systems -o json > "$ARC_SYSTEMS_JSON"
kubectl get pods -n arc-runners -o json > "$ARC_RUNNERS_JSON"
kubectl api-resources | grep -Ei 'runner|autoscaling' > "$ARC_RESOURCES_TXT" || true

python3 - "$NODE_JSON" "$ARC_SYSTEMS_JSON" "$ARC_RUNNERS_JSON" "$SUMMARY_JSON" <<'PY'
import json, sys
from pathlib import Path

node_path, systems_path, runners_path, summary_path = map(Path, sys.argv[1:])

nodes = json.loads(node_path.read_text())
systems = json.loads(systems_path.read_text())
runners = json.loads(runners_path.read_text())

def ready(obj):
    for condition in obj.get("status", {}).get("conditions", []):
        if condition.get("type") == "Ready":
            return condition.get("status") == "True"
    return False

node_items = nodes.get("items", [])
if not node_items:
    raise SystemExit("no Kubernetes nodes found")
if not all(ready(n) for n in node_items):
    raise SystemExit("one or more Kubernetes nodes are not Ready")

system_items = systems.get("items", [])
if not system_items:
    raise SystemExit("no ARC controller/listener pods found in arc-systems")
if not all(ready(p) for p in system_items):
    raise SystemExit("one or more arc-systems pods are not Ready")

runner_items = runners.get("items", [])
# minRunners=0 is intentional. Before a job is queued there should be no persistent runner pod.
persistent_runner_count = len(runner_items)
if persistent_runner_count != 0:
    raise SystemExit(f"expected zero standing runner pods before dispatch, found {persistent_runner_count}")

summary = {
    "decision": "ARC_RUNTIME_PRE_DISPATCH_READY",
    "kubernetes_nodes_ready": True,
    "arc_systems_ready": True,
    "standing_runner_count": persistent_runner_count,
    "expected_scale_set": "p0-data-certifier",
    "ephemeral_lifecycle_verified": False,
    "dataset_certified": False,
    "frozen_dataset": False,
    "paper_authorized": False,
    "testnet_authorized": False,
    "live_authorized": False,
}
summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(json.dumps(summary, indent=2, sort_keys=True))
PY

printf 'P0-DATA pre-dispatch runtime verification PASS\n'
printf 'Evidence: %s\n' "$SUMMARY_JSON"
