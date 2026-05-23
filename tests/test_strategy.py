import unittest

from app.strategy import Action, GridArbitrageEngine, Portfolio, StrategyConfig


class GridArbitrageEngineTest(unittest.TestCase):
    def test_portfolio_starts_with_usdt_inventory(self):
        config = StrategyConfig(total_capital_usd=30_000, tranche_count=10)
        portfolio = Portfolio.from_config(config)

        self.assertEqual(portfolio.usd_available, 0)
        self.assertEqual(portfolio.usdt_available, 30_000)
        self.assertEqual(config.tranche_size_usd, 3000)

    def test_sell_when_price_reaches_sell_floor(self):
        config = StrategyConfig(total_capital_usd=30_000, tranche_count=10)
        portfolio = Portfolio.from_config(config)
        decision = GridArbitrageEngine(config).evaluate(1.0, portfolio)

        self.assertEqual(decision.action, Action.SELL)
        self.assertEqual(decision.notional_usd, 3000)
        self.assertEqual(decision.grid_index, 1)

    def test_hold_below_sell_floor_without_open_sell_tranche(self):
        config = StrategyConfig(total_capital_usd=30_000, tranche_count=10)
        portfolio = Portfolio.from_config(config)
        decision = GridArbitrageEngine(config).evaluate(0.9994, portfolio)

        self.assertEqual(decision.action, Action.HOLD)
        self.assertEqual(decision.reason, "price is inside quiet band")

    def test_buy_back_after_sell_cycle_reaches_profit(self):
        config = StrategyConfig(total_capital_usd=30_000, tranche_count=10, fee_bps=0, slippage_bps=0)
        engine = GridArbitrageEngine(config)
        portfolio = Portfolio.from_config(config)

        sell_decision = engine.evaluate(1.0, portfolio)
        engine.apply(sell_decision, portfolio)
        buy_decision = engine.evaluate(0.9994, portfolio)

        self.assertEqual(buy_decision.action, Action.BUY)
        self.assertEqual(buy_decision.tranche_id, portfolio.open_tranches[0].id)
        self.assertGreaterEqual(buy_decision.expected_profit_bps, config.min_profit_bps)

    def test_apply_cycle_increases_usdt_inventory_and_realized_profit(self):
        config = StrategyConfig(total_capital_usd=30_000, tranche_count=10, fee_bps=0, slippage_bps=0)
        engine = GridArbitrageEngine(config)
        portfolio = Portfolio.from_config(config)

        sell_decision = engine.evaluate(1.0, portfolio)
        engine.apply(sell_decision, portfolio)
        buy_decision = engine.evaluate(0.9994, portfolio)
        engine.apply(buy_decision, portfolio)

        self.assertEqual(len(portfolio.open_tranches), 0)
        self.assertGreater(portfolio.usdt_available, 30_000)
        self.assertGreater(portfolio.realized_profit_usd, 0)

    def test_same_price_can_repeat_after_previous_tranche_is_closed(self):
        config = StrategyConfig(total_capital_usd=30_000, tranche_count=10, fee_bps=0, slippage_bps=0)
        engine = GridArbitrageEngine(config)
        portfolio = Portfolio.from_config(config)

        first_sell = engine.evaluate(1.0, portfolio)
        engine.apply(first_sell, portfolio)
        first_buy = engine.evaluate(0.9994, portfolio)
        engine.apply(first_buy, portfolio)

        second_sell = engine.evaluate(1.0, portfolio)
        engine.apply(second_sell, portfolio)
        second_buy = engine.evaluate(0.9994, portfolio)

        self.assertEqual(second_sell.action, Action.SELL)
        self.assertEqual(second_buy.action, Action.BUY)

    def test_same_price_does_not_create_duplicate_while_previous_order_is_open(self):
        config = StrategyConfig(total_capital_usd=30_000, tranche_count=10, fee_bps=0, slippage_bps=0)
        engine = GridArbitrageEngine(config)
        portfolio = Portfolio.from_config(config)

        first_sell = engine.evaluate(1.0, portfolio)
        engine.apply(first_sell, portfolio)
        second_sell = engine.evaluate(1.0, portfolio)

        self.assertEqual(first_sell.action, Action.SELL)
        self.assertEqual(second_sell.action, Action.SELL)
        self.assertEqual(second_sell.grid_index, 2)

    def test_buyback_requires_minimum_profit(self):
        config = StrategyConfig(total_capital_usd=30_000, tranche_count=10, fee_bps=0, slippage_bps=0)
        engine = GridArbitrageEngine(config)
        portfolio = Portfolio.from_config(config)

        sell_decision = engine.evaluate(1.0, portfolio)
        engine.apply(sell_decision, portfolio)
        hold_decision = engine.evaluate(0.9996, portfolio)

        self.assertEqual(hold_decision.action, Action.HOLD)

    def test_tranche_count_can_be_twenty(self):
        config = StrategyConfig(total_capital_usd=20_000, tranche_count=20, max_open_tranches=20)

        self.assertEqual(config.tranche_size_usd, 1000)

    def test_tranche_count_cannot_exceed_twenty(self):
        with self.assertRaises(ValueError):
            StrategyConfig(tranche_count=21)

    def test_total_capital_must_stay_in_allowed_range(self):
        with self.assertRaises(ValueError):
            StrategyConfig(total_capital_usd=499)
        with self.assertRaises(ValueError):
            StrategyConfig(total_capital_usd=200_001)

    def test_max_open_tranches_cannot_exceed_tranche_count(self):
        with self.assertRaises(ValueError):
            StrategyConfig(tranche_count=5, max_open_tranches=6)


if __name__ == "__main__":
    unittest.main()
