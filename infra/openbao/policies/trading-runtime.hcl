# Runtime identity receives only short-lived, scoped credentials.
# No withdrawal, root, policy-management or static master-secret paths are exposed.

path "secret/data/trading/{{identity.entity.aliases.auth_jwt_*.metadata.environment}}/broker/read-only" {
  capabilities = ["read"]
}

path "database/creds/trading-runtime" {
  capabilities = ["read"]
}

path "transit/encrypt/evidence-ledger" {
  capabilities = ["update"]
}

path "transit/decrypt/evidence-ledger" {
  capabilities = ["update"]
}

path "sys/*" {
  capabilities = ["deny"]
}

path "auth/*" {
  capabilities = ["deny"]
}

path "secret/data/*/withdrawal*" {
  capabilities = ["deny"]
}
