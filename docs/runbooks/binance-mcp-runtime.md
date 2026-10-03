# Binance MCP Runtime CLI

The Runtime may invoke `scripts/binance_mcp_cli.py` only through a fixed
operation allowlist and a request JSON file placed under the configured
`BINANCE_MCP_REQUEST_ROOT`.

Default handlers are read-only Binance Spot market/account operations.
Side-effecting operation names are recognized by the boundary but deliberately
have no default handler. A later certified runtime increment must install the
domain handler only after exact-intent approval, deterministic risk, OMS and
reconciliation gates are present.

Secrets are loaded from systemd credentials and are never accepted in the
request JSON. The request boundary rejects caller-controlled URL, command,
shell and module fields and redacts sensitive output keys.

Withdrawals, transfers, margin, futures and options are not supported.
