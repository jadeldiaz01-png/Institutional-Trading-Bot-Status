"""Pure, fail-closed contracts for the Binance MCP trading domain."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
import re
from typing import Literal

from .canonical import sha256_json

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DecisionAction = Literal["BUY", "SELL", "HOLD", "NO_TRADE"]
TradingEnvironment = Literal["PAPER", "TESTNET", "LIVE_PILOT", "LIMITED_LIVE"]
OrderSide = Literal["BUY", "SELL"]


def _nonblank(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank")


def _sha256(name: str, value: str) -> None:
    if SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be lowercase SHA-256")


def _decimal(name: str, value: str, *, positive: bool = True, allow_zero: bool = False) -> Decimal:
    try:
        parsed = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"{name} must be decimal text") from exc
    if not parsed.is_finite():
        raise ValueError(f"{name} must be finite")
    if positive and (parsed < 0 or (parsed == 0 and not allow_zero)):
        raise ValueError(f"{name} must be positive")
    return parsed


@dataclass(frozen=True)
class ModelDecision:
    model_provider: str
    model_id: str
    model_version: str
    request_id: str
    timestamp_ms: int
    symbol: str
    horizon: str
    action: DecisionAction
    confidence: float
    rationale_summary: str
    evidence_refs: tuple[str, ...]
    assumptions: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    risk_factors: tuple[str, ...]
    uncertainty: float
    data_freshness_ms: int
    input_snapshot_sha256: str

    def __post_init__(self) -> None:
        for name in ("model_provider", "model_id", "model_version", "request_id", "symbol", "horizon", "rationale_summary"):
            _nonblank(name, getattr(self, name))
        if self.action not in {"BUY", "SELL", "HOLD", "NO_TRADE"}:
            raise ValueError("invalid model action")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not 0.0 <= self.uncertainty <= 1.0:
            raise ValueError("uncertainty must be between 0 and 1")
        if self.timestamp_ms < 0 or self.data_freshness_ms < 0:
            raise ValueError("timestamps/freshness must be nonnegative")
        _sha256("input_snapshot_sha256", self.input_snapshot_sha256)


@dataclass(frozen=True)
class BinancePermissions:
    read: bool = False
    spot_trade: bool = False
    withdrawals: bool = False
    internal_transfer: bool = False
    universal_transfer: bool = False
    margin: bool = False
    futures: bool = False


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    captured_at_ms: int
    bid: str
    ask: str
    last: str

    def __post_init__(self) -> None:
        _nonblank("symbol", self.symbol)
        if self.captured_at_ms < 0:
            raise ValueError("captured_at_ms must be nonnegative")
        bid = _decimal("bid", self.bid)
        ask = _decimal("ask", self.ask)
        _decimal("last", self.last)
        if bid > ask:
            raise ValueError("bid cannot exceed ask")


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reasons: tuple[str, ...]
    snapshot_sha256: str

    def __post_init__(self) -> None:
        _sha256("snapshot_sha256", self.snapshot_sha256)
        if not self.allowed and not self.reasons:
            raise ValueError("denied risk decision requires reasons")


@dataclass(frozen=True)
class TradeIntent:
    account_alias: str
    environment: TradingEnvironment
    symbol: str
    side: OrderSide
    order_type: str
    quantity: str | None
    quote_quantity: str | None
    price: str | None
    stop_price: str | None
    time_in_force: str | None
    max_slippage_bps: str
    max_notional: str
    strategy_id: str
    strategy_version: str
    risk_snapshot_sha256: str
    model_bundle_sha256: str
    market_snapshot_sha256: str
    exchange_info_sha256: str
    created_at_ms: int
    expires_at_ms: int

    def __post_init__(self) -> None:
        for name in ("account_alias", "symbol", "order_type", "strategy_id", "strategy_version"):
            _nonblank(name, getattr(self, name))
        if self.environment not in {"PAPER", "TESTNET", "LIVE_PILOT", "LIMITED_LIVE"}:
            raise ValueError("invalid trading environment")
        if self.side not in {"BUY", "SELL"}:
            raise ValueError("invalid side")
        if (self.quantity is None) == (self.quote_quantity is None):
            raise ValueError("exactly one of quantity or quote_quantity is required")
        if self.quantity is not None:
            _decimal("quantity", self.quantity)
        if self.quote_quantity is not None:
            _decimal("quote_quantity", self.quote_quantity)
        if self.price is not None:
            _decimal("price", self.price)
        if self.stop_price is not None:
            _decimal("stop_price", self.stop_price)
        _decimal("max_slippage_bps", self.max_slippage_bps, positive=True, allow_zero=True)
        _decimal("max_notional", self.max_notional)
        for name in (
            "risk_snapshot_sha256",
            "model_bundle_sha256",
            "market_snapshot_sha256",
            "exchange_info_sha256",
        ):
            _sha256(name, getattr(self, name))
        if self.created_at_ms < 0 or self.expires_at_ms <= self.created_at_ms:
            raise ValueError("intent expiration must be after creation")

    def intent_sha256(self) -> str:
        return sha256_json(self)


@dataclass(frozen=True)
class OrderApproval:
    approval_id: str
    intent_sha256: str
    account_alias: str
    environment: TradingEnvironment
    symbol: str
    side: OrderSide
    order_type: str
    quantity: str | None
    quote_quantity: str | None
    price: str | None
    stop_price: str | None
    time_in_force: str | None
    max_slippage_bps: str
    max_notional: str
    strategy_id: str
    strategy_version: str
    risk_snapshot_sha256: str
    model_bundle_sha256: str
    market_snapshot_sha256: str
    exchange_info_sha256: str
    created_at_ms: int
    expires_at_ms: int
    nonce: str

    def __post_init__(self) -> None:
        _nonblank("approval_id", self.approval_id)
        _nonblank("nonce", self.nonce)
        _sha256("intent_sha256", self.intent_sha256)
        if self.expires_at_ms <= self.created_at_ms:
            raise ValueError("approval expiration must be after creation")

    @classmethod
    def from_intent(
        cls,
        *,
        approval_id: str,
        intent: TradeIntent,
        nonce: str,
        created_at_ms: int,
        expires_at_ms: int,
    ) -> "OrderApproval":
        return cls(
            approval_id=approval_id,
            intent_sha256=intent.intent_sha256(),
            account_alias=intent.account_alias,
            environment=intent.environment,
            symbol=intent.symbol,
            side=intent.side,
            order_type=intent.order_type,
            quantity=intent.quantity,
            quote_quantity=intent.quote_quantity,
            price=intent.price,
            stop_price=intent.stop_price,
            time_in_force=intent.time_in_force,
            max_slippage_bps=intent.max_slippage_bps,
            max_notional=intent.max_notional,
            strategy_id=intent.strategy_id,
            strategy_version=intent.strategy_version,
            risk_snapshot_sha256=intent.risk_snapshot_sha256,
            model_bundle_sha256=intent.model_bundle_sha256,
            market_snapshot_sha256=intent.market_snapshot_sha256,
            exchange_info_sha256=intent.exchange_info_sha256,
            created_at_ms=created_at_ms,
            expires_at_ms=expires_at_ms,
            nonce=nonce,
        )


class OrderState(str, Enum):
    PROPOSED = "PROPOSED"
    VALIDATED = "VALIDATED"
    RISK_APPROVED = "RISK_APPROVED"
    HUMAN_APPROVAL_PENDING = "HUMAN_APPROVAL_PENDING"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    SUBMITTING = "SUBMITTING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    UNKNOWN = "UNKNOWN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    RECONCILED = "RECONCILED"


@dataclass(frozen=True)
class OrderRecord:
    order_id: str
    intent_sha256: str
    idempotency_key: str
    client_order_id: str
    state: OrderState
    authorization_id: str | None = None
    reconciliation_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("order_id", "idempotency_key", "client_order_id"):
            _nonblank(name, getattr(self, name))
        _sha256("intent_sha256", self.intent_sha256)
