from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class Environment(StrEnum):
    PAPER = "PAPER"
    TESTNET = "TESTNET"
    PROD = "PROD"


class IntentState(StrEnum):
    CREATED = "CREATED"
    POLICY_APPROVED = "POLICY_APPROVED"
    RISK_APPROVED = "RISK_APPROVED"
    SUBMITTING = "SUBMITTING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    SUSPENDED = "SUSPENDED"


TERMINAL_STATES = {
    IntentState.FILLED,
    IntentState.CANCELLED,
    IntentState.REJECTED,
    IntentState.SUSPENDED,
}


class OrderIntent(BaseModel):
    intent_id: UUID = Field(default_factory=uuid4)
    client_order_id: str = Field(min_length=8, max_length=128)
    idempotency_key: str = Field(min_length=16, max_length=256)
    environment: Environment
    account_ref: str = Field(min_length=1, max_length=128)
    strategy_id: str = Field(min_length=1, max_length=128)
    strategy_version: str = Field(min_length=1, max_length=64)
    symbol: str = Field(min_length=1, max_length=32)
    side: str = Field(pattern="^(BUY|SELL)$")
    quantity: Decimal = Field(gt=0)
    order_type: str = Field(pattern="^(MARKET|LIMIT|STOP|STOP_LIMIT)$")
    limit_price: Decimal | None = Field(default=None, gt=0)
    signal_ref: str = Field(min_length=1, max_length=256)
    approval_ref: str | None = None
    policy_decision_ref: str | None = None
    risk_decision_ref: str | None = None
    state: IntentState = IntentState.CREATED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def enforce_prod_human_approval(self) -> "OrderIntent":
        if self.environment == Environment.PROD and not self.approval_ref:
            raise ValueError("PROD intent requires explicit human approval_ref")
        return self

    def canonical_fingerprint(self) -> str:
        material = "|".join(
            [
                self.environment,
                self.account_ref,
                self.strategy_id,
                self.strategy_version,
                self.symbol,
                self.side,
                str(self.quantity),
                self.order_type,
                str(self.limit_price or ""),
                self.signal_ref,
            ]
        )
        return sha256(material.encode("utf-8")).hexdigest()
