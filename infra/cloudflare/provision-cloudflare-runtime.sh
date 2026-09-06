#!/usr/bin/env bash
set -euo pipefail

: "${CLOUDFLARE_ACCOUNT_ID:?required}"
: "${CLOUDFLARE_API_TOKEN:?required}"
: "${R2_BUCKET:?required}"

TUNNEL_NAME="${CLOUDFLARE_TUNNEL_NAME:-p0-data-certifier}"
API="https://api.cloudflare.com/client/v4"
AUTH=(-H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" -H 'Content-Type: application/json')

mkdir -p artifacts/p0_data_runtime

verify=$(curl -fsS "${AUTH[@]}" "${API}/user/tokens/verify")
python - <<'PY' "$verify"
import json,sys
j=json.loads(sys.argv[1]); assert j.get('success') is True
print('CLOUDFLARE_TOKEN_VERIFIED')
PY

tunnels=$(curl -fsS "${AUTH[@]}" "${API}/accounts/${CLOUDFLARE_ACCOUNT_ID}/cfd_tunnel?is_deleted=false")
tunnel_id=$(python - <<'PY' "$tunnels" "$TUNNEL_NAME"
import json,sys
j=json.loads(sys.argv[1]); name=sys.argv[2]
for t in j.get('result',[]):
    if t.get('name')==name:
        print(t['id']); break
PY
)

if [[ -z "$tunnel_id" ]]; then
  created=$(curl -fsS -X POST "${AUTH[@]}" \
    "${API}/accounts/${CLOUDFLARE_ACCOUNT_ID}/cfd_tunnel" \
    --data "{\"name\":\"${TUNNEL_NAME}\",\"config_src\":\"cloudflare\"}")
  tunnel_id=$(python - <<'PY' "$created"
import json,sys
j=json.loads(sys.argv[1]); assert j.get('success') is True; print(j['result']['id'])
PY
)
fi

# R2 bucket creation is idempotent: treat existing bucket as success.
code=$(curl -sS -o /tmp/r2-create.json -w '%{http_code}' -X PUT "${AUTH[@]}" \
  "${API}/accounts/${CLOUDFLARE_ACCOUNT_ID}/r2/buckets/${R2_BUCKET}")
if [[ "$code" != "200" && "$code" != "201" && "$code" != "409" ]]; then
  cat /tmp/r2-create.json >&2
  exit 1
fi

python - <<'PY' "$tunnel_id" "$TUNNEL_NAME" "$R2_BUCKET"
import json,sys,datetime,pathlib
out={
  'decision':'CLOUDFLARE_RUNTIME_PROVISIONED',
  'tunnel_id':sys.argv[1],
  'tunnel_name':sys.argv[2],
  'r2_bucket':sys.argv[3],
  'secrets_committed':False,
  'dataset_certified':False,
  'frozen_dataset':False,
  'paper_authorized':False,
  'testnet_authorized':False,
  'live_authorized':False,
  'verified_at':datetime.datetime.now(datetime.timezone.utc).isoformat()
}
path=pathlib.Path('artifacts/p0_data_runtime/cloudflare-runtime.json')
path.write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
PY
