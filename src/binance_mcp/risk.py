"""Deterministic fail-closed risk evaluation for governed Spot candidates."""

from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal, InvalidOperation
from typing import Any

from .binance_public import SymbolFilters
from .canonical import sha256_json
from .contracts import MarketSnapshot, RiskDecision, TradeIntent


def _d(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("invalid decimal policy/input") from exc
    if not result.is_finite():
        raise ValueError("non-finite decimal policy/input")
    return result


def _multiple(value: Decimal, step: Decimal) -> bool:
    if step <= 0:
        return False
    return value.remainder_near(step) == 0


@dataclass(frozen=True)
class RiskPolicy:
    max_order_notional: str | None
    max_spread_bps: str | None
    max_slippage_bps: str | None
    max_concentration_pct: str | None
    max_daily_loss: str | None
    max_strategy_drawdown_pct: str | None
    max_simultaneous_positions: int | None
    min_cash_reserve: str | None

    def complete(self) -> bool:
        return all(getattr(self, item.name) is not None for item in fields(self))


@dataclass(frozen=True)
class PortfolioSnapshot:
    total_equity: str
    cash_available: str
    current_symbol_exposure: str
    daily_pnl: str
    strategy_drawdown_pct: str
    open_positions: int


@dataclass(frozen=True)
class SystemHealth:
    binance_connected: bool
    websocket_healthy: bool
    clock_synchronized: bool
    reconciliation_clean: bool
    telemetry_healthy: bool
    policy_healthy: bool
    secrets_healthy: bool
    permissions_healthy: bool
    kill_switch_clear: bool

    def healthy(self) -> bool:
        return all(getattr(self, item.name) is True for item in fields(self))


class RiskEngine:
    def __init__(self, policy: RiskPolicy):
        self.policy = policy

    def _decision(
        self,
        reasons: list[str],
        *,
        intent: TradeIntent,
        market: MarketSnapshot,
        portfolio: PortfolioSnapshot,
        symbol_filters: SymbolFilters,
        system_health: SystemHealth,
    ) -> RiskDecision:
        snapshot = sha256_json(
            {
                "policy": self.policy,
                "intent": intent,
                "market": market,
                "portfolio": portfolio,
                "symbol_filters": symbol_filters,
                "system_health": system_health,
                "reasons": tuple(reasons),
            }
        )
        return RiskDecision(allowed=not reasons, reasons=tuple(reasons), snapshot_sha256=snapshot)

    def evaluate(
        self,
        intent: TradeIntent,
        market: MarketSnapshot,
        portfolio: PortfolioSnapshot,
        symbol_filters: SymbolFilters,
        system_health: SystemHealth,
    ) -> RiskDecision:
        reasons: list[str] = []

        if not self.policy.complete():
            reasons.append("POLICY_INCOMPLETE")
            return self._decision(
                reasons,
                intent=intent,
                market=market,
                portfolio=portfolio,
                symbol_filters=symbol_filters,
                system_health=system_health,
            )

        if not system_health.healthy():
            reasons.append("SYSTEM_UNHEALTHY")

        if intent.symbol != market.symbol or intent.symbol != symbol_filters.symbol:
            reasons.append("SYMBOL_MISMATCH")

        if symbol_filters.status != "TRADING":
            reasons.append("SYMBOL_NOT_TRADING")
        if intent.order_type not in symbol_filters.order_types:
            reasons.append("ORDER_TYPE_NOT_ALLOWED")

        price = _d(intent.price) if intent.price is not None else _d(market.last)
        quantity = _d(intent.quantity)
        quote_quantity = _d(intent.quote_quantity)
        assert price is not None

        notional: Decimal
        if quantity is not None:
            notional = quantity * price
        elif quote_quantity is not None:
            notional = quote_quantity
        else:
            reasons.append("ORDER_SIZE_MISSING")
            notional = Decimal("0")

        policy_max_notional = _d(self.policy.max_order_notional)
        intent_max_notional = _d(intent.max_notional)
        if (
            policy_max_notional is None
            or intent_max_notional is None
            or notional > policy_max_notional
            or notional > intent_max_notional
        ):
            reasons.append("MAX_ORDER_NOTIONAL")

        bid = _d(market.bid)
        ask = _d(market.ask)
        assert bid is not None and ask is not None
        midpoint = (bid + ask) / Decimal("2")
        spread_bps = ((ask - bid) / midpoint * Decimal("10000")) if midpoint > 0 else Decimal("Infinity")
        max_spread = _d(self.policy.max_spread_bps)
        if max_spread is None or spread_bps > max_spread:
            reasons.append("MAX_SPREAD_BPS")

        max_slippage = _d(self.policy.max_slippage_bps)
        requested_slippage = _d(intent.max_slippage_bps)
        if max_slippage is None or requested_slippage is None or requested_slippage > max_slippage:
            reasons.append("MAX_SLIPPAGE_BPS")

        total_equity = _d(portfolio.total_equity)
        current_exposure = _d(portfolio.current_symbol_exposure)
        max_concentration = _d(self.policy.max_concentration_pct)
        if total_equity is None or current_exposure is None or total_equity <= 0 or max_concentration is None:
            reasons.append("MAX_CONCENTRATION")
        else:
            post_trade_exposure = current_exposure + notional
            concentration_pct = post_trade_exposure / total_equity * Decimal("100")
            if concentration_pct > max_concentration:
                reasons.append("MAX_CONCENTRATION")

        daily_pnl = _d(portfolio.daily_pnl)
        max_daily_loss = _d(self.policy.max_daily_loss)
        if daily_pnl is None or max_daily_loss is None or daily_pnl < -max_daily_loss:
            reasons.append("MAX_DAILY_LOSS")

        drawdown = _d(portfolio.strategy_drawdown_pct)
        max_drawdown = _d(self.policy.max_strategy_drawdown_pct)
        if drawdown is None or max_drawdown is None or drawdown > max_drawdown:
            reasons.append("MAX_STRATEGY_DRAWDOWN")

        max_positions = self.policy.max_simultaneous_positions
        if (
            max_positions is None
            or max_positions < 0
            or portfolio.open_positions < 0
            or portfolio.open_positions >= max_positions
        ):
            reasons.append("MAX_SIMULTANEOUS_POSITIONS")

        cash = _d(portfolio.cash_available)
        min_cash = _d(self.policy.min_cash_reserve)
        if cash is None or min_cash is None or cash - notional < min_cash:
            reasons.append("MIN_CASH_RESERVE")

        tick = _d(symbol_filters.tick_size)
        if intent.price is not None and (tick is None or not _multiple(price, tick)):
            reasons.append("PRICE_FILTER")

        if quantity is not None:
            step = _d(symbol_filters.step_size)
            min_qty = _d(symbol_filters.min_qty)
            max_qty = _d(symbol_filters.max_qty)
            if (
                step is None
                or min_qty is None
                or max_qty is None
                or not _multiple(quantity, step)
                or quantity < min_qty
                or quantity > max_qty
            ):
                reasons.append("LOT_SIZE")

        min_notional = _d(symbol_filters.min_notional)
        max_filter_notional = _d(symbol_filters.max_notional)
        if min_notional is not None and notional < min_notional:
            reasons.append("MIN_NOTIONAL")
        if max_filter_notional is not None and notional > max_filter_notional:
            reasons.append("MAX_NOTIONAL_FILTER")

        # Preserve deterministic ordering while avoiding duplicate reason codes.
        deduped = list(dict.fromkeys(reasons))
        return self._decision(
            deduped,
            intent=intent,
            market=market,
            portfolio=portfolio,
            symbol_filters=symbol_filters,
            system_health=system_health,
        )
