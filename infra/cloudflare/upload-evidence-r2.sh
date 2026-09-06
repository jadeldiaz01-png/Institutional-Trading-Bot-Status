#!/usr/bin/env bash
set -euo pipefail

: "${R2_ACCOUNT_ID:?R2_ACCOUNT_ID is required}"
: "${R2_BUCKET:?R2_BUCKET is required}"
: "${AWS_ACCESS_KEY_ID:?AWS_ACCESS_KEY_ID is required}"
: "${AWS_SECRET_ACCESS_KEY:?AWS_SECRET_ACCESS_KEY is required}"

EVIDENCE_DIR="${1:-artifacts/ar_tf_v1d2_dataset}"
RUN_ID="${GITHUB_RUN_ID:-manual}"
CODE_SHA="${GITHUB_SHA:-unknown}"
PREFIX="p0-data-001/${CODE_SHA}/${RUN_ID}"
ENDPOINT="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

command -v aws >/dev/null 2>&1 || { echo 'aws CLI is required' >&2; exit 1; }
command -v sha256sum >/dev/null 2>&1 || { echo 'sha256sum is required' >&2; exit 1; }
[[ -d "$EVIDENCE_DIR" ]] || { echo "Evidence directory missing: $EVIDENCE_DIR" >&2; exit 1; }

export AWS_REGION=auto
MANIFEST="${EVIDENCE_DIR%/}/SHA256SUMS"
find "$EVIDENCE_DIR" -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > "$MANIFEST"

aws s3 cp "$EVIDENCE_DIR" "s3://${R2_BUCKET}/${PREFIX}/" \
  --recursive \
  --only-show-errors \
  --endpoint-url "$ENDPOINT"

aws s3 cp "$MANIFEST" "s3://${R2_BUCKET}/${PREFIX}/SHA256SUMS" \
  --only-show-errors \
  --endpoint-url "$ENDPOINT"

printf 'R2_EVIDENCE_UPLOADED\nbucket=%s\nprefix=%s\nsha=%s\n' "$R2_BUCKET" "$PREFIX" "$CODE_SHA"
