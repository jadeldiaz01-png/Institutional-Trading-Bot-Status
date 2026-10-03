ui = false
disable_mlock = false

storage "file" {
  path = "/openbao/file"
}

listener "tcp" {
  address = "0.0.0.0:8200"
  tls_disable = 1
}

api_addr = "http://openbao:8200"
cluster_addr = "http://openbao:8201"

default_lease_ttl = "15m"
max_lease_ttl = "1h"

# TESTNET container config only. TLS termination and workload OIDC binding must
# be supplied by the deployment environment before any non-local use.
