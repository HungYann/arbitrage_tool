import unittest
import os
from unittest.mock import patch

os.environ.setdefault("ARBITRAGE_AUTO_TRADE_ENABLED", "false")
os.environ["TELEGRAM_ALERT_ENABLED"] = "false"

from fastapi.testclient import TestClient

from app.auth import CAPTCHA_COOKIE, SESSION_COOKIE, create_admin_captcha_challenge, create_admin_session
from app import main
from app.main import app


class ApiBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.client.post("/reset")
        main.pending_auto_order.clear()

    def login_admin(self):
        captcha = "ABCD2"
        self.client.cookies.set(CAPTCHA_COOKIE, create_admin_captcha_challenge(captcha), domain="testserver.local", path="/admin")
        response = self.client.post(
            "/admin/login",
            json={
                "username": os.getenv("ADMIN_USERNAME", "admin"),
                "password": os.getenv("ADMIN_PASSWORD", ""),
                "captcha": captcha,
            },
        )
        return response

    def authenticate_broker_actions(self):
        self.client.cookies.set(SESSION_COOKIE, create_admin_session(os.getenv("ADMIN_USERNAME", "admin")), domain="testserver.local", path="/")

    def test_balance_alias_returns_portfolio(self):
        response = self.client.get("/balance")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["usd_available"], 0.0)
        self.assertEqual(data["usdt_available"], 30000.0)
        self.assertEqual(data["open_tranches"], [])

    def test_trade_endpoint_executes_initial_sell_strategy_in_service(self):
        sell = self.client.post("/trade", json={"price": 1.0, "execute": False})
        state = self.client.get("/state").json()

        self.assertEqual(sell.status_code, 200)
        self.assertEqual(sell.json()["action"], "sell")
        self.assertTrue(sell.json()["executed"])
        self.assertEqual(len(state["open_tranches"]), 1)

    def test_tick_can_evaluate_without_execution(self):
        decision = self.client.post("/tick", json={"price": 1.0, "execute": False})
        state = self.client.get("/state").json()

        self.assertEqual(decision.status_code, 200)
        self.assertEqual(decision.json()["action"], "sell")
        self.assertFalse(decision.json()["executed"])
        self.assertEqual(len(state["open_tranches"]), 0)

    def test_broker_trade_uses_service_strategy_and_simulated_order(self):
        self.authenticate_broker_actions()

        class FakeBroker:
            def __init__(self):
                self.config = type("Config", (), {"max_live_order_notional_usd": 0})()

            def quote(self):
                return {"symbol": "USDTUSD", "base_asset": "USDT", "quote_asset": "USD", "bid": 1.0, "ask": 1.0001, "mid": 1.00005}

            def place_limit_buy(self, quote_order_qty, limit_price):
                return {"status": "SIMULATED", "would_place_order": {"type": "LIMIT", "quoteNotional": str(quote_order_qty), "price": str(limit_price)}}

            def place_limit_sell(self, quantity, limit_price):
                return {"status": "SIMULATED", "would_place_order": {"type": "LIMIT", "quantity": str(quantity), "price": str(limit_price)}}

        with patch("app.main.BinanceSpotBroker", return_value=FakeBroker()):
            response = self.client.post("/broker/trade", json={})
            state = self.client.get("/state").json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["decision"]["action"], "sell")
        self.assertTrue(response.json()["decision"]["executed"])
        self.assertEqual(len(state["open_tranches"]), 1)

    def test_broker_trade_does_not_cap_live_order_notional(self):
        self.authenticate_broker_actions()
        captured = {}

        class FakeBroker:
            def __init__(self):
                self.config = type("Config", (), {"max_live_order_notional_usd": 999})()

            def quote(self):
                return {"symbol": "USDTUSD", "base_asset": "USDT", "quote_asset": "USD", "bid": 1.0, "ask": 1.0001, "mid": 1.00005}

            def place_limit_buy(self, quote_order_qty, limit_price):
                return {"status": "SIMULATED", "would_place_order": {"type": "LIMIT", "quoteNotional": str(quote_order_qty), "price": str(limit_price)}}

            def place_limit_sell(self, quantity, limit_price):
                captured["quantity"] = quantity
                captured["limit_price"] = limit_price
                return {"status": "SIMULATED", "would_place_order": {"type": "LIMIT", "quantity": str(quantity), "price": str(limit_price)}}

        payload = self.client.get("/config").json()
        payload["max_live_order_notional_usd"] = 25
        self.client.put("/config", json=payload)

        with patch("app.main.BinanceSpotBroker", return_value=FakeBroker()):
            response = self.client.post("/broker/trade", json={})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["quantity"], 3000)
        self.assertEqual(captured["limit_price"], 1.0)
        self.assertEqual(response.json()["decision"]["notional_usd"], 3000)
        self.assertNotIn("capped by max_live_order_notional_usd", response.json()["decision"]["reason"])

    def test_broker_trade_sends_telegram_alert_when_order_is_created(self):
        self.authenticate_broker_actions()

        class FakeBroker:
            def __init__(self):
                self.config = type("Config", (), {"max_live_order_notional_usd": 0})()

            def quote(self):
                return {"symbol": "USDTUSD", "base_asset": "USDT", "quote_asset": "USD", "bid": 1.0, "ask": 1.0001, "mid": 1.00005}

            def place_limit_buy(self, quote_order_qty, limit_price):
                return {"id": "order-1", "symbol": "USDT/USD", "status": "SIMULATED", "price": limit_price}

            def place_limit_sell(self, quantity, limit_price):
                return {"id": "sell-1", "symbol": "USDT/USD", "status": "SIMULATED", "price": limit_price}

        with patch("app.main.BinanceSpotBroker", return_value=FakeBroker()), patch("app.main.send_telegram_event") as send_alert:
            response = self.client.post("/broker/trade", json={})

        self.assertEqual(response.status_code, 200)
        send_alert.assert_called_once()
        self.assertEqual(send_alert.call_args.args[0], "broker_trade_requested")

    def test_telegram_test_endpoint_requires_admin_and_sends_message(self):
        self.authenticate_broker_actions()

        with patch("app.main.send_telegram_message", return_value={"ok": True}) as send_message:
            response = self.client.post("/telegram/test")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        self.assertIn("Open Arbitrage Telegram test", send_message.call_args.args[0])

    def test_auto_trade_tracks_pending_open_order(self):
        main.pending_auto_order.clear()

        class FakeBroker:
            def __init__(self):
                self.config = type("Config", (), {"max_live_order_notional_usd": 0, "ccxt_symbol": "USDT/USD"})()

            def quote(self):
                return {"symbol": "USDTUSD", "base_asset": "USDT", "quote_asset": "USD", "bid": 1.0, "ask": 1.0001, "mid": 1.00005}

            def place_limit_buy(self, quote_order_qty, limit_price):
                return {"id": "open-1", "symbol": "USDT/USD", "status": "open", "price": limit_price}

            def place_limit_sell(self, quantity, limit_price):
                return {"id": "sell-1", "symbol": "USDT/USD", "status": "open", "price": limit_price}

        with patch("app.main.BinanceSpotBroker", return_value=FakeBroker()):
            main.auto_trade_once()

        self.assertEqual(main.pending_auto_order["id"], "sell-1")
        self.assertEqual(main.pending_auto_order["decision"]["action"], "sell")

    def test_create_and_cancel_test_order(self):
        self.authenticate_broker_actions()

        class FakeBroker:
            def __init__(self):
                self.config = type("Config", (), {"max_live_order_notional_usd": 50, "ccxt_symbol": "USDT/USD"})()

            def quote(self):
                return {"symbol": "USDTUSD", "base_asset": "USDT", "quote_asset": "USD", "bid": 0.9993, "ask": 0.9995, "mid": 0.9994}

            def visible_limit_buy_price(self, quote, price_multiplier=0.9999):
                return quote["bid"] - 0.0001

            def place_limit_buy(self, quote_order_qty, limit_price):
                return {"id": "test-1", "symbol": "USDT/USD", "status": "open", "price": limit_price, "amount": quote_order_qty / limit_price}

            def cancel_order(self, order_id, symbol=None):
                return {"id": order_id, "symbol": symbol, "status": "canceled"}

        with patch("app.main.BinanceSpotBroker", return_value=FakeBroker()):
            created = self.client.post("/broker/test-order?notional_usd=10&price_multiplier=0.8")
            cancelled = self.client.post("/broker/test-order/cancel")

        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["test_order"]["id"], "test-1")
        self.assertAlmostEqual(created.json()["test_order"]["limit_price"], 0.9992)
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.json()["cancel"]["status"], "canceled")

    def test_broker_quote_can_report_websocket_warmup(self):
        with patch("app.main.quote_stream.latest_quote", return_value=None):
            response = self.client.get("/broker/quote?source=websocket")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "warming_up")

    def test_broker_ws_start_accepts_force_restart_flag(self):
        with patch("app.main.quote_stream.start", return_value={"running": True, "symbol": "USDTUSD"}) as start:
            response = self.client.post("/broker/ws/start?force=true")

        self.assertEqual(response.status_code, 200)
        start.assert_called_once_with(force=True)

    def test_admin_realtime_returns_quote_stream_and_events(self):
        login = self.login_admin()
        self.assertEqual(login.status_code, 200)
        self.client.cookies.set(SESSION_COOKIE, create_admin_session(os.getenv("ADMIN_USERNAME", "admin")), domain="testserver.local", path="/admin")

        response = self.client.get("/admin/api/realtime?limit=5")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("server_time_utc8", data)
        self.assertIn("quote_stream", data)
        self.assertIn("recent_events", data)
        self.assertIn("symbol", data["quote_stream"])

    def test_admin_api_requires_authentication(self):
        response = TestClient(app).get("/admin/api/realtime?limit=5")

        self.assertEqual(response.status_code, 401)
        self.assertIn(SESSION_COOKIE, response.headers.get("set-cookie", ""))
        self.assertIn("Max-Age=0", response.headers.get("set-cookie", ""))

    def test_admin_page_clears_invalid_session_and_requires_password(self):
        client = TestClient(app)
        client.cookies.set(SESSION_COOKIE, "invalid-session", domain="testserver.local", path="/admin")

        response = client.get("/admin")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Open Arbitrage Admin Login", response.text)
        self.assertIn("Please sign in to continue.", response.text)
        self.assertIn(SESSION_COOKIE, response.headers.get("set-cookie", ""))
        self.assertIn("Max-Age=0", response.headers.get("set-cookie", ""))

    def test_admin_login_rejects_bad_password(self):
        captcha = "ABCD2"
        self.client.cookies.set(CAPTCHA_COOKIE, create_admin_captcha_challenge(captcha), domain="testserver.local", path="/admin")

        response = self.client.post("/admin/login", json={"username": "admin", "password": "wrong", "captcha": captcha})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Invalid username or password.")
        self.assertEqual(response.json()["reason"], "invalid_credentials")
        self.assertIn("Max-Age=0", response.headers.get("set-cookie", ""))

    def test_admin_login_rejects_bad_captcha(self):
        captcha = "ABCD2"
        self.client.cookies.set(CAPTCHA_COOKIE, create_admin_captcha_challenge(captcha), domain="testserver.local", path="/admin")

        response = self.client.post(
            "/admin/login",
            json={
                "username": os.getenv("ADMIN_USERNAME", "admin"),
                "password": os.getenv("ADMIN_PASSWORD", ""),
                "captcha": "WRONG",
            },
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Invalid or expired verification code.")
        self.assertEqual(response.json()["reason"], "invalid_captcha")
        self.assertIn("Max-Age=0", response.headers.get("set-cookie", ""))

    def test_admin_login_page_is_not_cached(self):
        response = self.client.get("/admin/login")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store, max-age=0")

    def test_admin_captcha_returns_image_and_challenge_cookie(self):
        response = self.client.get("/admin/captcha")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/svg+xml")
        self.assertIn("<svg", response.text)
        self.assertIn(CAPTCHA_COOKIE, response.headers.get("set-cookie", ""))


if __name__ == "__main__":
    unittest.main()
