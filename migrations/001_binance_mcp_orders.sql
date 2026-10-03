PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS binance_mcp_orders (
    order_id TEXT PRIMARY KEY,
    intent_sha256 TEXT NOT NULL UNIQUE,
    idempotency_key TEXT NOT NULL UNIQUE,
    client_order_id TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL,
    authorization_id TEXT,
    reconciliation_id TEXT
);

CREATE TABLE IF NOT EXISTS binance_mcp_approval_nonces (
    nonce TEXT PRIMARY KEY,
    consumed_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
