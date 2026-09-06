#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-artifacts/p0_data_runtime}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-1800}"
POLL_SECONDS="${POLL_SECONDS:-2}"
mkdir -p "$OUT_DIR"

EVENTS="$OUT_DIR/ephemeral-runner-events.ndjson"
SUMMARY="$OUT_DIR/ephemeral-runner-lifecycle.json"
: > "$EVENTS"

command -v kubectl >/dev/null 2>&1 || { echo 'kubectl not found' >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo 'python3 not found' >&2; exit 1; }

count_runner_pods() {
  kubectl get pods -n arc-runners -o json | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("items", [])))'
}

record() {
  local phase="$1" count="$2"
  python3 - "$phase" "$count" >> "$EVENTS" <<'PY'
import json,sys,datetime
print(json.dumps({
  "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
  "phase": sys.argv[1],
  "runner_pod_count": int(sys.argv[2]),
}, sort_keys=True))
PY
}

initial="$(count_runner_pods)"
record initial "$initial"
if [[ "$initial" -ne 0 ]]; then
  echo "expected 0 runner pods before dispatch; found $initial" >&2
  exit 1
fi

deadline=$(( $(date +%s) + TIMEOUT_SECONDS ))
seen_runner=0
seen_cleanup=0
max_count=0

while (( $(date +%s) < deadline )); do
  count="$(count_runner_pods)"
  (( count > max_count )) && max_count="$count"

  if [[ "$seen_runner" -eq 0 && "$count" -gt 0 ]]; then
    seen_runner=1
    record runner_created "$count"
  elif [[ "$seen_runner" -eq 1 && "$count" -eq 0 ]]; then
    seen_cleanup=1
    record runner_deleted "$count"
    break
  fi
  sleep "$POLL_SECONDS"
done

python3 - "$seen_runner" "$seen_cleanup" "$max_count" "$SUMMARY" <<'PY'
import json,sys
from pathlib import Path
created = bool(int(sys.argv[1]))
deleted = bool(int(sys.argv[2]))
max_count = int(sys.argv[3])
path = Path(sys.argv[4])
verified = created and deleted and max_count >= 1
summary = {
  "decision": "ARC_EPHEMERAL_LIFECYCLE_VERIFIED" if verified else "ARC_EPHEMERAL_LIFECYCLE_NOT_VERIFIED",
  "runner_created_observed": created,
  "runner_deleted_observed": deleted,
  "max_runner_pod_count": max_count,
  "ephemeral_lifecycle_verified": verified,
  "dataset_certified": False,
  "frozen_dataset": False,
  "paper_authorized": False,
  "testnet_authorized": False,
  "live_authorized": False,
}
path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(json.dumps(summary, indent=2, sort_keys=True))
if not verified:
    raise SystemExit(1)
PY
