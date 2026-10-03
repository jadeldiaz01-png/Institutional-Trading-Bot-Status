from __future__ import annotations

import unittest
from dataclasses import replace

from binance_mcp.binance_public import SymbolFilters
from binance_mcp.contracts import MarketSnapshot, TradeIntent
from binance_mcp.risk import PortfolioSnapshot, RiskEngine, RiskPolicy, SystemHealth


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64


def intent(*, quantity="0.001", price="50000.00", max_slippage_bps="25") -> TradeIntent:
    return TradeIntent(
        account_alias="spot-primary",
        environment="TESTNET",
        symbol="BTCUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=quantity,
        quote_quantity=None,
        price=price,
        stop_price=None,
        time_in_force="GTC",
        max_slippage_bps=max_slippage_bps,
        max_notional="100.00",
        strategy_id="manual-reviewed",
        strategy_version="1",
        risk_snapshot_sha256=SHA_A,
        model_bundle_sha256=SHA_B,
        market_snapshot_sha256=SHA_C,
        exchange_info_sha256=SHA_D,
        created_at_ms=1_800_000_000_000,
        expires_at_ms=1_800_000_060_000,
    )


def market(*, bid="49999.00", ask="50001.00", last="50000.00") -> MarketSnapshot:
    return MarketSnapshot(
        symbol="BTCUSDT",
        captured_at_ms=1_800_000_000_100,
        bid=bid,
        ask=ask,
        last=last,
    )


def filters() -> SymbolFilters:
    return SymbolFilters(
        symbol="BTCUSDT",
        status="TRADING",
        order_types=("LIMIT", "MARKET"),
        tick_size="0.01",
        step_size="0.001",
        min_qty="0.001",
        max_qty="10.000",
        min_notional="10.00",
        max_notional="100000.00",
    )


def policy(**overrides) -> RiskPolicy:
    values = dict(
        max_order_notional="100.00",
        max_spread_bps="10",
        max_slippage_bps="25",
        max_concentration_pct="50",
        max_daily_loss="100.00",
        max_strategy_drawdown_pct="10",
        max_simultaneous_positions=3,
        min_cash_reserve="50.00",
    )
    values.update(overrides)
    return RiskPolicy(**values)


def portfolio(**overrides) -> PortfolioSnapshot:
    values = dict(
        total_equity="1000.00",
        cash_available="500.00",
        current_symbol_exposure="100.00",
        daily_pnl="-10.00",
        strategy_drawdown_pct="2",
        open_positions=1,
    )
    values.update(overrides)
    return PortfolioSnapshot(**values)


def health(**overrides) -> SystemHealth:
    values = dict(
        binance_connected=True,
        websocket_healthy=True,
        clock_synchronized=True,
        reconciliation_clean=True,
        telemetry_healthy=True,
        policy_healthy=True,
        secrets_healthy=True,
        permissions_healthy=True,
        kill_switch_clear=True,
    )
    values.update(overrides)
    return SystemHealth(**values)


class RiskEngineTests(unittest.TestCase):
    def evaluate(self, *, p=None, i=None, m=None, port=None, h=None, f=None):
        return RiskEngine(p or policy()).evaluate(
            i or intent(),
            m or market(),
            port or portfolio(),
            f or filters(),
            h or health(),
        )

    def test_incomplete_policy_fails_closed(self):
        incomplete = RiskPolicy(
            max_order_notional=None,
            max_spread_bps=None,
            max_slippage_bps=None,
            max_concentration_pct=None,
            max_daily_loss=None,
            max_strategy_drawdown_pct=None,
            max_simultaneous_positions=None,
            min_cash_reserve=None,
        )
        result = self.evaluate(p=incomplete)
        self.assertFalse(result.allowed)
        self.assertIn("POLICY_INCOMPLETE", result.reasons)

    def test_order_notional_boundary_equal_passes_above_denies(self):
        equal = self.evaluate(i=intent(quantity="0.002", price="50000.00"))
        self.assertTrue(equal.allowed)
        above = self.evaluate(i=intent(quantity="0.003", price="50000.00"))
        self.assertFalse(above.allowed)
        self.assertIn("MAX_ORDER_NOTIONAL", above.reasons)

    def test_spread_boundary_and_slippage_boundary(self):
        at_spread = self.evaluate(m=market(bid="49975.00", ask="50025.00", last="50000.00"))
        self.assertTrue(at_spread.allowed)
        too_wide = self.evaluate(m=market(bid="49974.99", ask="50025.01", last="50000.00"))
        self.assertFalse(too_wide.allowed)
        self.assertIn("MAX_SPREAD_BPS", too_wide.reasons)

        self.assertTrue(self.evaluate(i=intent(max_slippage_bps="25")).allowed)
        too_much = self.evaluate(i=intent(max_slippage_bps="25.01"))
        self.assertFalse(too_much.allowed)
        self.assertIn("MAX_SLIPPAGE_BPS", too_much.reasons)

    def test_portfolio_boundaries_fail_closed(self):
        cases = [
            (portfolio(current_symbol_exposure="500.01"), "MAX_CONCENTRATION"),
            (portfolio(daily_pnl="-100.01"), "MAX_DAILY_LOSS"),
            (portfolio(strategy_drawdown_pct="10.01"), "MAX_STRATEGY_DRAWDOWN"),
            (portfolio(open_positions=4), "MAX_SIMULTANEOUS_POSITIONS"),
            (portfolio(cash_available="49.99"), "MIN_CASH_RESERVE"),
        ]
        for snapshot, reason in cases:
            with self.subTest(reason=reason):
                result = self.evaluate(port=snapshot)
                self.assertFalse(result.allowed)
                self.assertIn(reason, result.reasons)

    def test_system_health_failure_denies_new_side_effect(self):
        for field in (
            "binance_connected",
            "websocket_healthy",
            "clock_synchronized",
            "reconciliation_clean",
            "telemetry_healthy",
            "policy_healthy",
            "secrets_healthy",
            "permissions_healthy",
            "kill_switch_clear",
        ):
            result = self.evaluate(h=replace(health(), **{field: False}))
            self.assertFalse(result.allowed, field)
            self.assertIn("SYSTEM_UNHEALTHY", result.reasons)

    def test_exchange_filters_and_symbol_status_are_authoritative(self):
        bad_tick = self.evaluate(i=intent(price="50000.005"))
        self.assertFalse(bad_tick.allowed)
        self.assertIn("PRICE_FILTER", bad_tick.reasons)

        bad_step = self.evaluate(i=intent(quantity="0.0015"))
        self.assertFalse(bad_step.allowed)
        self.assertIn("LOT_SIZE", bad_step.reasons)

        halted = self.evaluate(f=replace(filters(), status="BREAK"))
        self.assertFalse(halted.allowed)
        self.assertIn("SYMBOL_NOT_TRADING", halted.reasons)

        unsupported = self.evaluate(f=replace(filters(), order_types=("MARKET",)))
        self.assertFalse(unsupported.allowed)
        self.assertIn("ORDER_TYPE_NOT_ALLOWED", unsupported.reasons)

    def test_minimum_notional_filter_denies_too_small_order(self):
        result = self.evaluate(i=intent(quantity="0.001", price="5000.00"))
        self.assertFalse(result.allowed)
        self.assertIn("MIN_NOTIONAL", result.reasons)


if __name__ == "__main__":
    unittest.main()
