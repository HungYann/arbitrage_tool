import unittest
from unittest.mock import patch

from app.broker import BinanceConfig, BinanceSpotBroker, format_decimal, parse_book_ticker


class BinanceBrokerTest(unittest.TestCase):
    def test_format_decimal_trims_trailing_zeroes(self):
        self.assertEqual(format_decimal(500.0), "500")
        self.assertEqual(format_decimal(0.123400), "0.1234")

    def test_quote_maps_book_ticker(self):
        broker = BinanceSpotBroker(
            BinanceConfig(symbol="USDTUSD", base_asset="USDT", quote_asset="USD", invert_price=False, ccxt_enabled=False)
        )
        with patch.object(
            broker,
            "_public_get",
            return_value={"symbol": "USDTUSD", "bidPrice": "0.9998", "askPrice": "1.0001"},
        ):
            quote = broker.quote()

        self.assertEqual(quote["symbol"], "USDTUSD")
        self.assertEqual(quote["quote_asset"], "USD")
        self.assertEqual(quote["bid"], 0.9998)
        self.assertEqual(quote["ask"], 1.0001)
        self.assertAlmostEqual(quote["mid"], 0.99995)

    def test_quote_can_invert_reverse_binance_symbol(self):
        broker = BinanceSpotBroker(
            BinanceConfig(symbol="USDCUSDT", base_asset="USDT", quote_asset="USDC", invert_price=True, ccxt_enabled=False)
        )
        with patch.object(
            broker,
            "_public_get",
            return_value={"symbol": "USDCUSDT", "bidPrice": "0.9998", "askPrice": "1.0001"},
        ):
            quote = broker.quote()

        self.assertEqual(quote["symbol"], "USDCUSDT")
        self.assertTrue(quote["price_inverted"])
        self.assertEqual(quote["quote_asset"], "USDC")
        self.assertAlmostEqual(quote["bid"], 1 / 1.0001)
        self.assertAlmostEqual(quote["ask"], 1 / 0.9998)

    def test_parse_websocket_book_ticker(self):
        quote = parse_book_ticker(
            {"u": 42, "s": "USDTUSD", "b": "0.9998", "B": "200.5", "a": "1.0001", "A": "300.25"},
            BinanceConfig(symbol="USDTUSD", base_asset="USDT", quote_asset="USD", invert_price=False),
        )

        self.assertEqual(quote["source"], "websocket")
        self.assertEqual(quote["stream"], "usdtusd@bookTicker")
        self.assertEqual(quote["quote_asset"], "USD")
        self.assertEqual(quote["bid_qty"], 200.5)
        self.assertEqual(quote["ask_qty"], 300.25)
        self.assertEqual(quote["update_id"], 42)

    def test_parse_combined_stream_book_ticker_payload(self):
        quote = parse_book_ticker(
            {
                "stream": "usdcusdt@bookTicker",
                "data": {"u": 42, "s": "USDCUSDT", "b": "0.9998", "B": "200.5", "a": "1.0001", "A": "300.25"},
            },
            BinanceConfig(symbol="USDCUSDT", base_asset="USDT", quote_asset="USDC", invert_price=True),
        )

        self.assertEqual(quote["stream"], "usdcusdt@bookTicker")
        self.assertEqual(quote["raw_symbol"], "USDCUSDT")
        self.assertAlmostEqual(quote["bid"], 1 / 1.0001)

    def test_market_order_is_simulated_unless_live_enabled(self):
        broker = BinanceSpotBroker(BinanceConfig(live_trading=False, invert_price=False, ccxt_enabled=False))
        order = broker.place_market_buy(500)

        self.assertFalse(order["live_trading"])
        self.assertEqual(order["status"], "SIMULATED")
        self.assertEqual(order["would_place_order"]["quoteOrderQty"], "500")

    def test_live_market_buy_respects_safety_cap(self):
        broker = BinanceSpotBroker(
            BinanceConfig(
                live_trading=True,
                invert_price=False,
                ccxt_enabled=False,
                max_live_order_notional_usd=50,
                api_key="key",
                api_secret="secret",
            )
        )

        with self.assertRaisesRegex(RuntimeError, "safety cap"):
            broker.place_market_buy(51)

    def test_limit_buy_builds_limit_payload_from_quote_notional(self):
        broker = BinanceSpotBroker(BinanceConfig(live_trading=False, invert_price=False, ccxt_enabled=True))
        order = broker.place_limit_buy(50, 0.9995)

        self.assertEqual(order["status"], "SIMULATED")
        self.assertEqual(order["would_place_order"]["type"], "LIMIT")
        self.assertEqual(order["would_place_order"]["side"], "BUY")
        self.assertEqual(order["would_place_order"]["timeInForce"], "GTC")
        self.assertEqual(order["would_place_order"]["price"], "0.9995")
        self.assertAlmostEqual(float(order["would_place_order"]["quantity"]), 50 / 0.9995)

    def test_ccxt_limit_order_passes_price_and_time_in_force(self):
        class FakeExchange:
            def create_order(self, symbol, order_type, side, amount, price, params):
                return {
                    "symbol": symbol,
                    "type": order_type,
                    "side": side,
                    "amount": amount,
                    "price": price,
                    "params": params,
                    "status": "open",
                }

        broker = BinanceSpotBroker(BinanceConfig(live_trading=True, ccxt_enabled=True, api_key="key", api_secret="secret"))
        with patch.object(broker, "_ccxt_exchange", return_value=FakeExchange()):
            order = broker.place_limit_buy(50, 0.9995)

        self.assertEqual(order["broker"], "ccxt")
        self.assertEqual(order["type"], "limit")
        self.assertEqual(order["side"], "buy")
        self.assertEqual(order["price"], 0.9995)
        self.assertEqual(order["params"]["timeInForce"], "GTC")

    def test_ccxt_limit_order_uses_exchange_precision(self):
        class FakeExchange:
            def load_markets(self):
                self.loaded = True

            def amount_to_precision(self, symbol, amount):
                return f"{amount:.2f}"

            def price_to_precision(self, symbol, price):
                return f"{price:.4f}"

            def market(self, symbol):
                return {"limits": {"price": {"min": 0.8, "max": 1.2}}}

            def create_order(self, symbol, order_type, side, amount, price, params):
                return {
                    "symbol": symbol,
                    "type": order_type,
                    "side": side,
                    "amount": amount,
                    "price": price,
                    "params": params,
                    "status": "open",
                }

        broker = BinanceSpotBroker(BinanceConfig(live_trading=True, ccxt_enabled=True, api_key="key", api_secret="secret"))
        with patch.object(broker, "_ccxt_exchange", return_value=FakeExchange()):
            order = broker.place_limit_buy(10, 0.7996123456)

        self.assertEqual(order["price"], 0.8)
        self.assertEqual(order["amount"], 12.51)

    def test_visible_limit_buy_price_uses_bid_below_one_tick(self):
        class FakeExchange:
            def load_markets(self):
                self.loaded = True

            def market(self, symbol):
                return {
                    "precision": {"price": 0.0001},
                    "limits": {"price": {"min": 0.8, "max": 1.2}},
                    "info": {"filters": [{"filterType": "PRICE_FILTER", "tickSize": "0.00010000"}]},
                }

            def price_to_precision(self, symbol, price):
                return f"{price:.4f}"

        broker = BinanceSpotBroker(BinanceConfig(live_trading=True, ccxt_enabled=True, api_key="key", api_secret="secret"))
        quote = {"bid": 0.9995, "ask": 0.9996}
        with patch.object(broker, "_ccxt_exchange", return_value=FakeExchange()):
            price = broker.visible_limit_buy_price(quote, 0.8)

        self.assertEqual(price, 0.9994)

    def test_ccxt_cancel_order(self):
        class FakeExchange:
            def cancel_order(self, order_id, symbol):
                return {"id": order_id, "symbol": symbol, "status": "canceled"}

        broker = BinanceSpotBroker(BinanceConfig(live_trading=True, ccxt_enabled=True, api_key="key", api_secret="secret"))
        with patch.object(broker, "_ccxt_exchange", return_value=FakeExchange()):
            order = broker.cancel_order("123", "USDT/USD")

        self.assertEqual(order["broker"], "ccxt")
        self.assertEqual(order["id"], "123")
        self.assertEqual(order["status"], "canceled")

    def test_ccxt_fetch_order(self):
        class FakeExchange:
            def fetch_order(self, order_id, symbol):
                return {"id": order_id, "symbol": symbol, "status": "closed"}

        broker = BinanceSpotBroker(BinanceConfig(live_trading=True, ccxt_enabled=True, api_key="key", api_secret="secret"))
        with patch.object(broker, "_ccxt_exchange", return_value=FakeExchange()):
            order = broker.fetch_order("123", "USDT/USD")

        self.assertEqual(order["broker"], "ccxt")
        self.assertEqual(order["id"], "123")
        self.assertEqual(order["status"], "closed")

    def test_inverted_market_buy_maps_to_reverse_pair_sell(self):
        broker = BinanceSpotBroker(
            BinanceConfig(symbol="USDCUSDT", base_asset="USDT", quote_asset="USDC", live_trading=False, invert_price=True)
        )
        order = broker.place_market_buy(500)

        self.assertEqual(order["would_place_order"]["side"], "SELL")
        self.assertEqual(order["would_place_order"]["quantity"], "500")
        self.assertEqual(order["intended_action"], "BUY_USDT_WITH_USDC")

    def test_ccxt_quote_maps_ticker(self):
        class FakeExchange:
            def fetch_ticker(self, symbol):
                return {
                    "symbol": symbol,
                    "bid": 0.9995,
                    "ask": 0.9996,
                    "bidVolume": 100,
                    "askVolume": 200,
                    "timestamp": 123456,
                }

        broker = BinanceSpotBroker(BinanceConfig(ccxt_enabled=True, ccxt_exchange_id="binance", ccxt_symbol="USDT/USD"))
        with patch.object(broker, "_ccxt_exchange", return_value=FakeExchange()):
            quote = broker.quote()

        self.assertEqual(quote["source"], "ccxt")
        self.assertEqual(quote["ccxt_exchange"], "binance")
        self.assertEqual(quote["ccxt_symbol"], "USDT/USD")
        self.assertEqual(quote["bid"], 0.9995)
        self.assertEqual(quote["ask"], 0.9996)

    def test_ccxt_balance_selects_base_and_quote_assets(self):
        class FakeExchange:
            def fetch_balance(self):
                return {
                    "USDT": {"free": 10, "used": 2, "total": 12},
                    "USD": {"free": 1000, "used": 50, "total": 1050},
                }

        broker = BinanceSpotBroker(BinanceConfig(ccxt_enabled=True))
        with patch.object(broker, "_ccxt_exchange", return_value=FakeExchange()):
            balance = broker.balance()

        self.assertEqual(balance["ccxt_exchange"], "binance")
        self.assertEqual(balance["balances"]["USDT"]["free"], 10)
        self.assertEqual(balance["balances"]["USD"]["locked"], 50)
