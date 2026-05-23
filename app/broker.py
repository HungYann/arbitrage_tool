from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import ssl
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class BinanceConfig:
    symbol: str = "USDTUSD"
    base_asset: str = "USDT"
    quote_asset: str = "USD"
    rest_url: str = "https://api.binance.com"
    ws_url: str = "wss://data-stream.binance.vision/ws"
    invert_price: bool = False
    ws_max_connection_seconds: int = 85_500
    ws_message_timeout_seconds: int = 15
    ccxt_enabled: bool = True
    ccxt_exchange_id: str = "binance"
    ccxt_symbol: str = "USDT/USD"
    ccxt_timeout_ms: int = 10_000
    recv_window: int = 5_000
    live_trading: bool = False
    max_live_order_notional_usd: float = 0.0
    api_key: str | None = None
    api_secret: str | None = None

    @classmethod
    def from_env(cls) -> "BinanceConfig":
        return cls(
            symbol=os.getenv("BINANCE_SYMBOL", "USDTUSD").upper(),
            base_asset=os.getenv("BINANCE_BASE_ASSET", "USDT").upper(),
            quote_asset=os.getenv("BINANCE_QUOTE_ASSET", "USD").upper(),
            rest_url=os.getenv("BINANCE_REST_URL", "https://api.binance.com").rstrip("/"),
            ws_url=os.getenv("BINANCE_WS_URL", "wss://data-stream.binance.vision/ws").rstrip("/"),
            invert_price=os.getenv("BINANCE_INVERT_PRICE", "false").lower() == "true",
            ws_max_connection_seconds=int(os.getenv("BINANCE_WS_MAX_CONNECTION_SECONDS", "85500")),
            ws_message_timeout_seconds=int(os.getenv("BINANCE_WS_MESSAGE_TIMEOUT_SECONDS", "15")),
            ccxt_enabled=os.getenv("CCXT_ENABLED", "true").lower() == "true",
            ccxt_exchange_id=os.getenv("CCXT_EXCHANGE_ID", "binance"),
            ccxt_symbol=os.getenv("CCXT_SYMBOL", "USDT/USD").upper(),
            ccxt_timeout_ms=int(os.getenv("CCXT_TIMEOUT_MS", "10000")),
            recv_window=int(os.getenv("BINANCE_RECV_WINDOW", "5000")),
            live_trading=os.getenv("BINANCE_LIVE_TRADING", "false").lower() == "true",
            max_live_order_notional_usd=float(os.getenv("BINANCE_MAX_LIVE_ORDER_NOTIONAL_USD", "0")),
            api_key=os.getenv("BINANCE_API_KEY"),
            api_secret=os.getenv("BINANCE_API_SECRET"),
        )


class BinanceSpotBroker:
    def __init__(self, config: BinanceConfig | None = None):
        self.config = config or BinanceConfig.from_env()

    def quote(self) -> dict[str, Any]:
        if self.config.ccxt_enabled:
            return self._ccxt_quote()
        return self._native_quote()

    def _native_quote(self) -> dict[str, Any]:
        data = self._public_get("/api/v3/ticker/bookTicker", {"symbol": self.config.symbol})
        return map_book_ticker(
            {
                "symbol": data.get("symbol", self.config.symbol),
                "bid": float(data["bidPrice"]),
                "ask": float(data["askPrice"]),
                "bid_qty": float(data.get("bidQty", 0)),
                "ask_qty": float(data.get("askQty", 0)),
                "source": "rest",
            },
            self.config,
        )

    def balance(self) -> dict[str, Any]:
        if self.config.ccxt_enabled:
            return self._ccxt_balance()

        account = self._signed_request("GET", "/api/v3/account", {})
        balances = account.get("balances", [])
        selected = {
            row["asset"]: {
                "free": float(row["free"]),
                "locked": float(row["locked"]),
                "total": float(row["free"]) + float(row["locked"]),
            }
            for row in balances
            if row.get("asset") in {self.config.base_asset, self.config.quote_asset}
        }
        return {
            "symbol": self.config.symbol,
            "base_asset": self.config.base_asset,
            "quote_asset": self.config.quote_asset,
            "balances": selected,
        }

    def place_market_buy(self, quote_order_qty: float) -> dict[str, Any]:
        if self.config.invert_price:
            payload = {
                "symbol": self.config.symbol,
                "side": "SELL",
                "type": "MARKET",
                "quantity": format_decimal(quote_order_qty),
                "newOrderRespType": "FULL",
            }
            metadata = {"intended_action": f"BUY_{self.config.base_asset}_WITH_{self.config.quote_asset}"}
        else:
            payload = {
                "symbol": self.config.symbol,
                "side": "BUY",
                "type": "MARKET",
                "quoteOrderQty": format_decimal(quote_order_qty),
                "newOrderRespType": "FULL",
            }
            metadata = {"intended_action": f"BUY_{self.config.base_asset}"}
        return self._place_order(payload, metadata)

    def place_market_sell(self, quantity: float) -> dict[str, Any]:
        if self.config.invert_price:
            payload = {
                "symbol": self.config.symbol,
                "side": "BUY",
                "type": "MARKET",
                "quoteOrderQty": format_decimal(quantity),
                "newOrderRespType": "FULL",
            }
            metadata = {"intended_action": f"SELL_{self.config.base_asset}_FOR_{self.config.quote_asset}"}
        else:
            payload = {
                "symbol": self.config.symbol,
                "side": "SELL",
                "type": "MARKET",
                "quantity": format_decimal(quantity),
                "newOrderRespType": "FULL",
            }
            metadata = {"intended_action": f"SELL_{self.config.base_asset}"}
        return self._place_order(payload, metadata)

    def place_limit_buy(self, quote_order_qty: float, limit_price: float) -> dict[str, Any]:
        quantity = quote_order_qty / limit_price
        payload = {
            "symbol": self.config.symbol,
            "side": "BUY",
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": format_decimal(quantity),
            "price": format_decimal(limit_price),
            "newOrderRespType": "FULL",
        }
        metadata = {
            "intended_action": f"BUY_{self.config.base_asset}",
            "quote_notional": format_decimal(quote_order_qty),
            "limit_price": format_decimal(limit_price),
        }
        return self._place_order(payload, metadata)

    def place_limit_sell(self, quantity: float, limit_price: float) -> dict[str, Any]:
        payload = {
            "symbol": self.config.symbol,
            "side": "SELL",
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": format_decimal(quantity),
            "price": format_decimal(limit_price),
            "newOrderRespType": "FULL",
        }
        metadata = {
            "intended_action": f"SELL_{self.config.base_asset}",
            "limit_price": format_decimal(limit_price),
        }
        return self._place_order(payload, metadata)

    def cancel_order(self, order_id: str, symbol: str | None = None) -> dict[str, Any]:
        if self.config.ccxt_enabled:
            exchange = self._ccxt_exchange()
            order = exchange.cancel_order(str(order_id), symbol or self.config.ccxt_symbol)
            return {
                "broker": "ccxt",
                "ccxt_exchange": self.config.ccxt_exchange_id,
                "ccxt_symbol": symbol or self.config.ccxt_symbol,
                **order,
            }
        return self._signed_request("DELETE", "/api/v3/order", {"symbol": symbol or self.config.symbol, "orderId": order_id})

    def fetch_order(self, order_id: str, symbol: str | None = None) -> dict[str, Any]:
        if self.config.ccxt_enabled:
            exchange = self._ccxt_exchange()
            order = exchange.fetch_order(str(order_id), symbol or self.config.ccxt_symbol)
            return {
                "broker": "ccxt",
                "ccxt_exchange": self.config.ccxt_exchange_id,
                "ccxt_symbol": symbol or self.config.ccxt_symbol,
                **order,
            }
        return self._signed_request("GET", "/api/v3/order", {"symbol": symbol or self.config.symbol, "orderId": order_id})

    def visible_limit_buy_price(self, quote: dict[str, Any], price_multiplier: float = 0.9999) -> float:
        fallback = float(quote["bid"]) * price_multiplier
        if not self.config.ccxt_enabled:
            return fallback

        exchange = self._ccxt_exchange()
        if hasattr(exchange, "load_markets"):
            exchange.load_markets()
        market = exchange.market(self.config.ccxt_symbol) if hasattr(exchange, "market") else None
        tick_size = market_price_tick_size(market)
        bid = float(quote["bid"])
        candidate = bid - tick_size
        candidate = max(candidate, tick_size)
        if hasattr(exchange, "price_to_precision"):
            candidate = float(exchange.price_to_precision(self.config.ccxt_symbol, candidate))
        return clamp_limit_price(candidate, market)

    def _place_order(self, payload: dict[str, Any], metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.config.live_trading:
            return {
                "live_trading": False,
                "broker": "ccxt" if self.config.ccxt_enabled else "binance_native",
                "would_place_order": payload,
                **(metadata or {}),
                "status": "SIMULATED",
            }
        self._validate_live_order(payload)
        if self.config.ccxt_enabled:
            response = self._ccxt_place_order(payload)
            return {**response, **(metadata or {})}
        response = self._signed_request("POST", "/api/v3/order", payload)
        return {**response, **(metadata or {})}

    def _validate_live_order(self, payload: dict[str, Any]) -> None:
        if self.config.max_live_order_notional_usd <= 0:
            return
        notional = None
        if "quoteOrderQty" in payload:
            notional = float(payload["quoteOrderQty"])
        elif payload.get("side") == "BUY" and "quantity" in payload and "price" in payload:
            notional = float(payload["quantity"]) * float(payload["price"])
        if notional is None:
            return
        if notional > self.config.max_live_order_notional_usd:
            raise RuntimeError(
                "live order rejected by safety cap: "
                f"notional {notional} exceeds BINANCE_MAX_LIVE_ORDER_NOTIONAL_USD "
                f"{self.config.max_live_order_notional_usd}"
            )

    def _ccxt_quote(self) -> dict[str, Any]:
        exchange = self._ccxt_exchange()
        ticker = exchange.fetch_ticker(self.config.ccxt_symbol)
        bid = float(ticker["bid"])
        ask = float(ticker["ask"])
        quote = map_book_ticker(
            {
                "symbol": ticker.get("symbol", self.config.ccxt_symbol),
                "bid": bid,
                "ask": ask,
                "bid_qty": ticker.get("bidVolume"),
                "ask_qty": ticker.get("askVolume"),
                "source": "ccxt",
                "update_id": ticker.get("timestamp"),
            },
            self.config,
        )
        quote["ccxt_exchange"] = self.config.ccxt_exchange_id
        quote["ccxt_symbol"] = self.config.ccxt_symbol
        return quote

    def _ccxt_balance(self) -> dict[str, Any]:
        exchange = self._ccxt_exchange()
        account = exchange.fetch_balance()
        selected = {}
        for asset in {self.config.base_asset, self.config.quote_asset}:
            row = account.get(asset) or {}
            free = row.get("free", (account.get("free") or {}).get(asset, 0)) or 0
            used = row.get("used", (account.get("used") or {}).get(asset, 0)) or 0
            total = row.get("total", (account.get("total") or {}).get(asset, float(free) + float(used))) or 0
            selected[asset] = {
                "free": float(free),
                "locked": float(used),
                "total": float(total),
            }
        return {
            "symbol": self.config.symbol,
            "ccxt_exchange": self.config.ccxt_exchange_id,
            "ccxt_symbol": self.config.ccxt_symbol,
            "base_asset": self.config.base_asset,
            "quote_asset": self.config.quote_asset,
            "balances": selected,
        }

    def _ccxt_place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        exchange = self._ccxt_exchange()
        market = None
        if hasattr(exchange, "load_markets"):
            exchange.load_markets()
        if hasattr(exchange, "market"):
            market = exchange.market(self.config.ccxt_symbol)
        side = payload["side"].lower()
        amount = float(payload["quantity"]) if "quantity" in payload else None
        price = float(payload["price"]) if "price" in payload else None
        if amount is not None and hasattr(exchange, "amount_to_precision"):
            amount = float(exchange.amount_to_precision(self.config.ccxt_symbol, amount))
        if price is not None and hasattr(exchange, "price_to_precision"):
            price = clamp_limit_price(price, market)
            price = float(exchange.price_to_precision(self.config.ccxt_symbol, price))
            price = clamp_limit_price(price, market)
        order_type = payload["type"].lower()
        params = {}
        if "quoteOrderQty" in payload:
            params["quoteOrderQty"] = payload["quoteOrderQty"]
        if "timeInForce" in payload:
            params["timeInForce"] = payload["timeInForce"]
        order = exchange.create_order(self.config.ccxt_symbol, order_type, side, amount, price, params)
        return {
            "broker": "ccxt",
            "ccxt_exchange": self.config.ccxt_exchange_id,
            "ccxt_symbol": self.config.ccxt_symbol,
            **order,
        }

    def _ccxt_exchange(self) -> Any:
        try:
            import ccxt
        except ImportError as exc:
            raise RuntimeError("ccxt is not installed. Run `pip install -r requirements.txt`.") from exc

        try:
            exchange_cls = getattr(ccxt, self.config.ccxt_exchange_id)
        except AttributeError as exc:
            raise RuntimeError(f"Unknown CCXT exchange id: {self.config.ccxt_exchange_id}") from exc

        return exchange_cls(
            {
                "apiKey": self.config.api_key or "",
                "secret": self.config.api_secret or "",
                "enableRateLimit": True,
                "timeout": self.config.ccxt_timeout_ms,
                "options": {"defaultType": "spot"},
            }
        )

    def _public_get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        query = urllib.parse.urlencode(params)
        request = urllib.request.Request(f"{self.config.rest_url}{path}?{query}", method="GET")
        with urllib.request.urlopen(request, timeout=5, context=create_ssl_context()) as response:
            return json.loads(response.read().decode("utf-8"))

    def _signed_request(self, method: str, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.config.api_key or not self.config.api_secret:
            raise RuntimeError("BINANCE_API_KEY and BINANCE_API_SECRET are required for signed Binance requests.")

        signed = {
            **params,
            "timestamp": int(time.time() * 1000),
            "recvWindow": self.config.recv_window,
        }
        query = urllib.parse.urlencode(signed)
        signature = hmac.new(self.config.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
        body = f"{query}&signature={signature}".encode("utf-8")
        headers = {
            "X-MBX-APIKEY": self.config.api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        if method == "GET":
            request = urllib.request.Request(f"{self.config.rest_url}{path}?{body.decode('utf-8')}", headers=headers, method="GET")
        else:
            request = urllib.request.Request(f"{self.config.rest_url}{path}", data=body, headers=headers, method=method)

        with urllib.request.urlopen(request, timeout=10, context=create_ssl_context()) as response:
            return json.loads(response.read().decode("utf-8"))


class BinanceBookTickerStream:
    def __init__(self, config: BinanceConfig | None = None, reconnect_delay_seconds: float = 3.0):
        self.config = config or BinanceConfig.from_env()
        self.reconnect_delay_seconds = reconnect_delay_seconds
        self._latest: dict[str, Any] | None = None
        self._last_error: str | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    @property
    def stream_name(self) -> str:
        return f"{self.config.symbol.lower()}@bookTicker"

    @property
    def url(self) -> str:
        return f"{self.config.ws_url}/{self.stream_name}"

    def start(self, force: bool = False) -> dict[str, Any]:
        if self.is_running and not force:
            return self.status()
        if self.is_running and force:
            self.stop()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="binance-bookticker-ws", daemon=True)
        self._thread.start()
        return self.status()

    def stop(self) -> dict[str, Any]:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        return self.status()

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def latest_quote(self, max_age_seconds: float | None = None) -> dict[str, Any] | None:
        with self._lock:
            if self._latest is None:
                return None
            quote = dict(self._latest)
        if max_age_seconds is not None and time.time() - quote["received_at_epoch"] > max_age_seconds:
            return None
        quote.pop("received_at_epoch", None)
        return quote

    def status(self) -> dict[str, Any]:
        latest = self.latest_quote()
        return {
            "running": self.is_running,
            "symbol": self.config.symbol,
            "stream": self.stream_name,
            "url": self.url,
            "last_error": self._last_error,
            "latest": latest,
        }

    def _run(self) -> None:
        asyncio.run(self._listen_forever())

    async def _listen_forever(self) -> None:
        try:
            from websockets.legacy.client import connect
        except ImportError:  # pragma: no cover - depends on installed websockets version
            from websockets import connect

        while not self._stop_event.is_set():
            try:
                ssl_context = create_ssl_context() if self.url.startswith("wss://") else None
                async with connect(self.url, ping_interval=20, ping_timeout=20, ssl=ssl_context) as websocket:
                    connected_at = time.monotonic()
                    self._last_error = None
                    while not self._stop_event.is_set():
                        if time.monotonic() - connected_at >= self.config.ws_max_connection_seconds:
                            self._last_error = "reconnecting before Binance 24h WebSocket connection limit"
                            break
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=self.config.ws_message_timeout_seconds)
                        except asyncio.TimeoutError:
                            self._last_error = f"no Binance bookTicker message in {self.config.ws_message_timeout_seconds}s; reconnecting"
                            break
                        if self._stop_event.is_set():
                            break
                        payload = json.loads(message)
                        if payload.get("e") == "serverShutdown":
                            self._last_error = "Binance serverShutdown event received; reconnecting"
                            break
                        quote = parse_book_ticker(payload, self.config)
                        with self._lock:
                            self._latest = quote
            except Exception as exc:  # pragma: no cover - network failures depend on environment
                self._last_error = str(exc)
                await asyncio.sleep(self.reconnect_delay_seconds)


def parse_book_ticker(payload: dict[str, Any], config: BinanceConfig) -> dict[str, Any]:
    if "stream" in payload and "data" in payload:
        payload = payload["data"]
    raw = {
        "symbol": payload.get("s", config.symbol),
        "bid": float(payload["b"]),
        "ask": float(payload["a"]),
        "bid_qty": float(payload["B"]),
        "ask_qty": float(payload["A"]),
        "update_id": payload.get("u"),
        "source": "websocket",
    }
    return map_book_ticker(raw, config)


def map_book_ticker(raw: dict[str, Any], config: BinanceConfig) -> dict[str, Any]:
    raw_bid = raw["bid"]
    raw_ask = raw["ask"]
    if config.invert_price:
        bid = 1 / raw_ask
        ask = 1 / raw_bid
    else:
        bid = raw_bid
        ask = raw_ask
    received_at = datetime.now(timezone.utc)
    quote = {
        "symbol": raw.get("symbol", config.symbol),
        "base_asset": config.base_asset,
        "quote_asset": config.quote_asset,
        "bid": bid,
        "ask": ask,
        "bid_qty": raw.get("bid_qty"),
        "ask_qty": raw.get("ask_qty"),
        "mid": (bid + ask) / 2,
        "raw_bid": raw_bid,
        "raw_ask": raw_ask,
        "raw_symbol": raw.get("symbol", config.symbol),
        "price_inverted": config.invert_price,
        "update_id": raw.get("update_id"),
        "source": raw.get("source"),
        "stream": f"{config.symbol.lower()}@bookTicker",
        "received_at": received_at.isoformat(),
        "received_at_epoch": received_at.timestamp(),
    }
    return quote


def create_ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def format_decimal(value: float) -> str:
    text = f"{value:.12f}".rstrip("0").rstrip(".")
    return text if text else "0"


def clamp_limit_price(price: float, market: dict[str, Any] | None) -> float:
    limits = (market or {}).get("limits") or {}
    price_limits = limits.get("price") or {}
    min_price = price_limits.get("min")
    max_price = price_limits.get("max")
    if min_price is not None and price < float(min_price):
        return float(min_price)
    if max_price is not None and price > float(max_price):
        return float(max_price)
    return price


def market_price_tick_size(market: dict[str, Any] | None) -> float:
    for item in ((market or {}).get("info") or {}).get("filters", []):
        if item.get("filterType") == "PRICE_FILTER" and item.get("tickSize"):
            return float(item["tickSize"])
    precision = ((market or {}).get("precision") or {}).get("price")
    if isinstance(precision, (float, int)) and precision > 0:
        return float(precision)
    return 0.0001
