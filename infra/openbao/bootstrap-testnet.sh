#!/usr/bin/env bash
set -euo pipefail

: "${BAO_ADDR:?required}"
: "${BAO_TOKEN:?required at bootstrap time only}"
: "${OIDC_DISCOVERY_URL:?required}"
: "${OIDC_BOUND_ISSUER:?required}"
: "${OIDC_AUDIENCE:?required}"
: "${WORKLOAD_SUBJECT:?required}"

bao policy write trading-runtime /openbao/policies/trading-runtime.hcl

if ! bao auth list -format=json | python -c 'import json,sys; d=json.load(sys.stdin); raise SystemExit(0 if "jwt/" in d else 1)'; then
  bao auth enable -path=jwt jwt
fi

bao write auth/jwt/config \
  oidc_discovery_url="$OIDC_DISCOVERY_URL" \
  bound_issuer="$OIDC_BOUND_ISSUER"

bao write auth/jwt/role/trading-testnet \
  role_type=jwt \
  bound_audiences="$OIDC_AUDIENCE" \
  user_claim=sub \
  bound_subject="$WORKLOAD_SUBJECT" \
  token_policies=trading-runtime \
  token_ttl=15m \
  token_max_ttl=1h \
  claim_mappings=environment=environment,service=service,repository=repository,ref=ref

# Configuration assertion: TESTNET identity is not accepted unless all expected
# claims are supplied by the deployment's JWT and validated by OpenBao.
bao read auth/jwt/role/trading-testnet >/dev/null
