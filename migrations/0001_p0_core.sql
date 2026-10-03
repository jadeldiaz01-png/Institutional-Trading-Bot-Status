BEGIN;

CREATE TYPE trading_environment AS ENUM ('PAPER','TESTNET','PROD');
CREATE TYPE order_intent_state AS ENUM (
  'CREATED','POLICY_APPROVED','RISK_APPROVED','SUBMITTING','ACKNOWLEDGED',
  'PARTIALLY_FILLED','FILLED','CANCELLED','REJECTED','UNKNOWN','SUSPENDED'
);

CREATE TABLE order_intents (
  intent_id uuid PRIMARY KEY,
  client_order_id text NOT NULL UNIQUE,
  idempotency_key text NOT NULL UNIQUE,
  fingerprint char(64) NOT NULL,
  environment trading_environment NOT NULL,
  account_ref text NOT NULL,
  strategy_id text NOT NULL,
  strategy_version text NOT NULL,
  symbol text NOT NULL,
  side text NOT NULL CHECK (side IN ('BUY','SELL')),
  quantity numeric(38,18) NOT NULL CHECK (quantity > 0),
  order_type text NOT NULL,
  limit_price numeric(38,18),
  signal_ref text NOT NULL,
  approval_ref text,
  policy_decision_ref text,
  risk_decision_ref text,
  state order_intent_state NOT NULL DEFAULT 'CREATED',
  version bigint NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (environment <> 'PROD' OR approval_ref IS NOT NULL)
);

CREATE TABLE broker_order_links (
  intent_id uuid PRIMARY KEY REFERENCES order_intents(intent_id),
  broker text NOT NULL,
  broker_order_id text,
  broker_status text,
  last_observed_at timestamptz,
  reconciliation_required boolean NOT NULL DEFAULT false
);

CREATE TABLE evidence_ledger (
  sequence bigserial PRIMARY KEY,
  event_id uuid NOT NULL UNIQUE,
  occurred_at timestamptz NOT NULL,
  actor text NOT NULL,
  event_type text NOT NULL,
  subject_ref text NOT NULL,
  payload_json jsonb NOT NULL,
  previous_hash char(64),
  event_hash char(64) NOT NULL UNIQUE
);

CREATE INDEX idx_order_intents_state ON order_intents(state);
CREATE INDEX idx_order_intents_reconcile ON order_intents(state, updated_at)
  WHERE state IN ('SUBMITTING','UNKNOWN','PARTIALLY_FILLED');

COMMIT;
