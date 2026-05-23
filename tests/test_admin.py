import tempfile
import unittest

from app.admin import build_admin_summary, to_utc8_iso, with_utc8_quote_time
from app.store import JsonlEventStore, RuntimeState
from app.strategy import GridArbitrageEngine, Portfolio, StrategyConfig


class AdminSummaryTest(unittest.TestCase):
    def test_summary_counts_actions_and_portfolio_metrics(self):
        config = StrategyConfig(total_capital_usd=50_000, tranche_count=10)
        state = RuntimeState(config)
        engine = GridArbitrageEngine(config)

        sell_decision = engine.evaluate(1.0, state.portfolio)
        engine.apply(sell_decision, state.portfolio)
        buy_decision = engine.evaluate(0.9994, state.portfolio)
        engine.apply(buy_decision, state.portfolio)

        events = [
            {
                "ts": "2026-05-15T00:00:00+00:00",
                "type": "tick",
                "payload": {
                    "request": {"price": 1.0, "execute": True},
                    "decision": {"action": "sell", "executed": True},
                    "state": {"realized_profit_usd": 0},
                },
            },
            {
                "ts": "2026-05-15T00:00:01+00:00",
                "type": "tick",
                "payload": {
                    "request": {"price": 0.9994, "execute": True},
                    "decision": {"action": "buy", "executed": True},
                    "state": {"realized_profit_usd": state.portfolio.realized_profit_usd},
                },
            },
        ]

        summary = build_admin_summary(state, events)

        self.assertEqual(summary["metrics"]["ticks"], 2)
        self.assertEqual(summary["metrics"]["buys"], 1)
        self.assertEqual(summary["metrics"]["sells"], 1)
        self.assertEqual(summary["metrics"]["executed"], 2)
        self.assertEqual(summary["metrics"]["open_tranches"], 0)
        self.assertGreater(summary["metrics"]["realized_profit_usd"], 0)
        self.assertEqual(len(summary["profit_points"]), 2)

    def test_event_store_tail_handles_corrupt_lines(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonlEventStore(temp_dir)
            store.append("tick", {"decision": {"action": "hold"}})
            with store.event_path.open("a", encoding="utf-8") as f:
                f.write("not-json\n")

            events = store.tail(2)

        self.assertEqual(events[0]["type"], "tick")
        self.assertEqual(events[1]["type"], "corrupt_log_line")

    def test_quote_time_converts_to_utc8(self):
        status = {
            "latest": {
                "received_at": "2026-05-15T08:00:00+00:00",
            }
        }

        enriched = with_utc8_quote_time(status)

        self.assertEqual(to_utc8_iso("2026-05-15T08:00:00+00:00"), "2026-05-15T16:00:00+08:00")
        self.assertEqual(enriched["latest"]["received_at_utc8"], "2026-05-15T16:00:00+08:00")


if __name__ == "__main__":
    unittest.main()
