from __future__ import annotations

import asyncio
import os
from dataclasses import asdict
from contextlib import suppress
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from dotenv import load_dotenv

from .admin import create_admin_router
from .auth import require_admin_api
from .broker import BinanceBookTickerStream, BinanceSpotBroker
from .schemas import BrokerTradeRequest, DecisionResponse, StateResponse, StrategyConfigPayload, TickRequest
from .store import JsonlEventStore, RuntimeState
from .strategy import Action, Decision, GridArbitrageEngine, StrategyConfig
from .telegram_alerts import send_telegram_event, send_telegram_message


load_dotenv()


def config_from_env() -> StrategyConfig:
    return StrategyConfig(
        total_capital_usd=float(os.getenv("ARBITRAGE_TOTAL_CAPITAL_USD", "30000")),
        tranche_count=int(os.getenv("ARBITRAGE_TRANCHE_COUNT", "10")),
        strategy_mode=os.getenv("ARBITRAGE_STRATEGY_MODE", "gradient"),
        reference_price=float(os.getenv("ARBITRAGE_REFERENCE_PRICE", "1.0")),
        buy_threshold_bps=float(os.getenv("ARBITRAGE_BUY_THRESHOLD_BPS", "5")),
        min_profit_bps=float(os.getenv("ARBITRAGE_MIN_PROFIT_BPS", "5")),
        fee_bps=float(os.getenv("ARBITRAGE_FEE_BPS", "0")),
        slippage_bps=float(os.getenv("ARBITRAGE_SLIPPAGE_BPS", "0")),
        min_notional_usd=float(os.getenv("ARBITRAGE_MIN_NOTIONAL_USD", "10")),
        max_open_tranches=int(os.getenv("ARBITRAGE_MAX_OPEN_TRANCHES", os.getenv("ARBITRAGE_TRANCHE_COUNT", "10"))),
        max_buy_price=float(os.getenv("ARBITRAGE_MAX_BUY_PRICE", "0.9994")),
        min_sell_price=float(os.getenv("ARBITRAGE_MIN_SELL_PRICE", "1.0")),
        grid_step=float(os.getenv("ARBITRAGE_GRID_STEP", "0.0005")),
        min_buy_price=float(os.getenv("ARBITRAGE_MIN_BUY_PRICE", "0.9900")),
        max_usdt_allocation_pct=float(os.getenv("ARBITRAGE_MAX_USDT_ALLOCATION_PCT", "1.0")),
        max_live_order_notional_usd=float(os.getenv("BINANCE_MAX_LIVE_ORDER_NOTIONAL_USD", "0")),
    )


app = FastAPI(
    title="Open Arbitrage Tool",
    version="0.1.0",
    description="Paper-trading FastAPI prototype for tranche-based USDT/USD arbitrage.",
)

state = RuntimeState(config_from_env())
store = JsonlEventStore()
quote_stream = BinanceBookTickerStream()
last_test_order: dict = {}
pending_auto_order: dict[str, Any] = {}
auto_trade_task: asyncio.Task | None = None
app.include_router(create_admin_router(state, store, quote_stream))


def record_event(event_type: str, payload: dict[str, Any], *, telegram: bool = False) -> None:
    store.append(event_type, payload)
    if telegram:
        send_telegram_event(event_type, payload)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


@app.on_event("startup")
def maybe_start_quote_stream() -> None:
    status = quote_stream.start()
    record_event("binance_ws_started", status)


@app.on_event("startup")
async def maybe_start_auto_trader() -> None:
    global auto_trade_task
    if os.getenv("ARBITRAGE_AUTO_TRADE_ENABLED", "true").lower() != "true":
        record_event("auto_trader_disabled", {"enabled": False})
        return
    interval_seconds = float(os.getenv("ARBITRAGE_AUTO_TRADE_INTERVAL_SECONDS", "5"))
    auto_trade_task = asyncio.create_task(auto_trade_loop(interval_seconds))
    record_event("auto_trader_started", {"interval_seconds": interval_seconds})


@app.on_event("shutdown")
async def stop_runtime_tasks() -> None:
    global auto_trade_task
    if auto_trade_task is not None:
        auto_trade_task.cancel()
        with suppress(asyncio.CancelledError):
            await auto_trade_task
        record_event("auto_trader_stopped", {})
        auto_trade_task = None
    if quote_stream.is_running:
        status = quote_stream.stop()
        record_event("binance_ws_stopped", status)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": os.getenv("TRADING_MODE", "paper")}


@app.get("/config")
def get_config() -> dict:
    return state.config_dict()


@app.put("/config")
def update_config(payload: StrategyConfigPayload) -> dict:
    state.config = StrategyConfig(**payload.model_dump())
    state.reset()
    store.append("config_updated", state.config_dict())
    return state.config_dict()


@app.get("/state", response_model=StateResponse)
def get_state() -> dict:
    return state.portfolio_dict()


@app.get("/balance", response_model=StateResponse)
def get_balance() -> dict:
    return state.portfolio_dict()


@app.get("/broker/quote")
def broker_quote(source: str = Query("auto", pattern="^(auto|rest|websocket)$")) -> dict:
    if source in {"auto", "websocket"}:
        realtime_quote = quote_stream.latest_quote(max_age_seconds=10)
        if realtime_quote is not None:
            return realtime_quote
        if source == "websocket":
            return {
                "status": "warming_up",
                "message": "No fresh Binance WebSocket quote is available yet.",
                "stream": quote_stream.status(),
            }

    broker = BinanceSpotBroker()
    try:
        quote = broker.quote()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Binance quote unavailable: {exc}") from exc
    quote.setdefault("source", "rest")
    return quote


@app.post("/broker/ws/start")
def start_broker_ws(force: bool = Query(False)) -> dict:
    status = quote_stream.start(force=force)
    store.append("binance_ws_started", status)
    return status


@app.post("/broker/ws/stop")
def stop_broker_ws() -> dict:
    status = quote_stream.stop()
    store.append("binance_ws_stopped", status)
    return status


@app.get("/broker/ws/status")
def broker_ws_status() -> dict:
    return quote_stream.status()


@app.get("/auto/status")
def auto_status() -> dict:
    return {
        "enabled": os.getenv("ARBITRAGE_AUTO_TRADE_ENABLED", "true").lower() == "true",
        "running": bool(auto_trade_task and not auto_trade_task.done()),
        "pending_order": pending_auto_order or None,
        "interval_seconds": float(os.getenv("ARBITRAGE_AUTO_TRADE_INTERVAL_SECONDS", "5")),
    }


@app.post("/telegram/test", dependencies=[Depends(require_admin_api)])
def telegram_test() -> dict:
    message = (
        "Open Arbitrage Telegram test\n"
        "Status: ok\n"
        f"Mode: {os.getenv('TRADING_MODE', 'paper')}\n"
        f"Symbol: {os.getenv('BINANCE_SYMBOL', 'USDTUSD')}"
    )
    return send_telegram_message(message)


@app.get("/broker/balance")
def broker_balance() -> dict:
    broker = BinanceSpotBroker()
    try:
        return broker.balance()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Binance balance unavailable: {exc}") from exc


@app.post("/tick", response_model=DecisionResponse)
def tick(payload: TickRequest) -> dict:
    engine = GridArbitrageEngine(state.config)
    decision = engine.evaluate(payload.price, state.portfolio)
    executed = False

    if payload.execute and decision.action != "hold":
        engine.apply(decision, state.portfolio)
        executed = True

    response = {
        **asdict(decision),
        "executed": executed,
    }
    record_event("tick", {"request": payload.model_dump(), "decision": response, "state": state.portfolio_dict()})
    return response


@app.post("/trade", response_model=DecisionResponse)
def trade(payload: TickRequest) -> dict:
    trade_payload = TickRequest(price=payload.price, execute=True)
    response = tick(trade_payload)
    record_event("trade_requested", {"request": payload.model_dump(), "decision": response, "state": state.portfolio_dict()})
    return response


@app.post("/broker/trade", dependencies=[Depends(require_admin_api)])
def broker_trade(payload: BrokerTradeRequest) -> dict:
    return execute_broker_trade(payload, event_type="broker_trade_requested")


def execute_broker_trade(payload: BrokerTradeRequest, event_type: str) -> dict:
    broker = BinanceSpotBroker()
    quote = quote_stream.latest_quote(max_age_seconds=10)
    if quote is None:
        try:
            quote = broker.quote()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Binance quote unavailable: {exc}") from exc
        quote.setdefault("source", "rest")
    engine = GridArbitrageEngine(state.config)
    if payload.price is not None:
        decision = engine.evaluate(payload.price, state.portfolio)
    else:
        sell_decision = engine.evaluate(quote["bid"], state.portfolio)
        decision = sell_decision if sell_decision.action == "sell" else engine.evaluate(quote["ask"], state.portfolio)

    order = None
    executed = False
    if decision.action == "sell" and not decision.tranche_id:
        quantity = decision.notional_usd / decision.price
        order = broker.place_limit_sell(quantity, decision.price)
        executed = is_order_filled(order)
    elif decision.action == "buy" and decision.tranche_id:
        order = broker.place_limit_buy(decision.notional_usd, decision.price)
        executed = is_order_filled(order)
    elif decision.action == "buy":
        order = broker.place_limit_buy(decision.notional_usd, decision.price)
        executed = is_order_filled(order)
    elif decision.action == "sell" and decision.tranche_id:
        tranche = next((item for item in state.portfolio.open_tranches if item.id == decision.tranche_id), None)
        if tranche is not None:
            order = broker.place_limit_sell(tranche.usdt_amount, decision.price)
            executed = is_order_filled(order)

    if executed:
        engine.apply(decision, state.portfolio)

    response = {
        **asdict(decision),
        "executed": executed,
    }
    event = {
        "request": payload.model_dump(),
        "quote": quote,
        "decision": response,
        "order": order,
        "state": state.portfolio_dict(),
    }
    record_event(event_type, event, telegram=bool(order))
    return event


async def auto_trade_loop(interval_seconds: float) -> None:
    while True:
        try:
            await asyncio.to_thread(auto_trade_once)
        except Exception as exc:  # pragma: no cover - depends on network/exchange state
            record_event("auto_trader_error", {"error": str(exc)})
        await asyncio.sleep(interval_seconds)


def auto_trade_once() -> None:
    if pending_auto_order:
        refresh_pending_auto_order()
        return
    event = execute_broker_trade(BrokerTradeRequest(), event_type="auto_trade_checked")
    order = event.get("order")
    decision = event.get("decision") or {}
    if order and not is_order_filled(order):
        order_id = str(order.get("id") or order.get("orderId") or "")
        if order_id:
            pending_auto_order.update(
                {
                    "id": order_id,
                    "symbol": order.get("symbol") or order.get("ccxt_symbol") or BinanceSpotBroker().config.ccxt_symbol,
                    "decision": decision,
                    "order": order,
                }
            )
            record_event("auto_order_pending", dict(pending_auto_order))


def refresh_pending_auto_order() -> None:
    order_id = pending_auto_order.get("id")
    symbol = pending_auto_order.get("symbol")
    if not order_id:
        pending_auto_order.clear()
        return
    broker = BinanceSpotBroker()
    order = broker.fetch_order(str(order_id), symbol)
    status = str(order.get("status", "")).lower()
    if is_order_filled(order):
        engine = GridArbitrageEngine(state.config)
        decision = pending_auto_order.get("decision") or {}
        engine.apply(type_decision(decision), state.portfolio)
        record_event("auto_order_filled", {"order": order, "state": state.portfolio_dict()})
        pending_auto_order.clear()
    elif status in {"canceled", "cancelled", "expired", "rejected"}:
        record_event("auto_order_closed_without_fill", {"order": order, "status": status})
        pending_auto_order.clear()
    else:
        pending_auto_order["order"] = order
        record_event("auto_order_still_pending", {"order_id": order_id, "symbol": symbol, "status": status or "unknown"})


@app.post("/broker/test-order", dependencies=[Depends(require_admin_api)])
def create_test_order(
    notional_usd: float = Query(10.0, ge=10.0),
    price_multiplier: float = Query(0.9999, gt=0.0, lt=1.0),
    force: bool = Query(False),
) -> dict:
    global last_test_order
    if last_test_order and not force:
        raise HTTPException(status_code=409, detail="A test order is already tracked. Cancel it first or pass force=true.")

    broker = BinanceSpotBroker()
    quote = quote_stream.latest_quote(max_age_seconds=10)
    if quote is None:
        try:
            quote = broker.quote()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Binance quote unavailable: {exc}") from exc
        quote.setdefault("source", "rest")

    if notional_usd < state.config.min_notional_usd:
        raise HTTPException(status_code=400, detail="Test order notional is below min_notional_usd.")

    limit_price = broker.visible_limit_buy_price(quote, price_multiplier)
    try:
        order = broker.place_limit_buy(notional_usd, limit_price)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Binance test order failed: {exc}") from exc

    order_id = str(order.get("id") or order.get("orderId") or "")
    last_test_order = {
        "id": order_id,
        "symbol": order.get("symbol") or broker.config.ccxt_symbol,
        "notional_usd": notional_usd,
        "limit_price": limit_price,
        "order": order,
    }
    event = {"quote": quote, "test_order": last_test_order}
    record_event("broker_test_order_created", event, telegram=True)
    return event


@app.post("/broker/test-order/cancel", dependencies=[Depends(require_admin_api)])
def cancel_test_order(order_id: str | None = Query(None), symbol: str | None = Query(None)) -> dict:
    global last_test_order
    target_order_id = order_id or last_test_order.get("id")
    target_symbol = symbol or last_test_order.get("symbol")
    if not target_order_id:
        raise HTTPException(status_code=404, detail="No tracked test order is available to cancel.")

    broker = BinanceSpotBroker()
    try:
        order = broker.cancel_order(str(target_order_id), target_symbol)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Binance cancel test order failed: {exc}") from exc

    event = {"order_id": target_order_id, "symbol": target_symbol, "cancel": order}
    record_event("broker_test_order_cancelled", event, telegram=True)
    last_test_order = {}
    return event


@app.get("/broker/test-order")
def get_test_order() -> dict:
    return {"test_order": last_test_order or None}


def is_order_filled(order: dict | None) -> bool:
    if not order:
        return False
    status = str(order.get("status", "")).upper()
    return status in {"FILLED", "CLOSED", "SIMULATED"}


def type_decision(data: dict[str, Any]) -> Decision:
    return Decision(
        action=Action(str(data.get("action", "hold"))),
        reason=str(data.get("reason", "")),
        price=float(data.get("price", 0)),
        notional_usd=float(data.get("notional_usd", 0)),
        tranche_id=data.get("tranche_id"),
        grid_index=data.get("grid_index"),
        expected_profit_usd=float(data.get("expected_profit_usd", 0)),
        expected_profit_bps=float(data.get("expected_profit_bps", 0)),
        expected_gross_profit_bps=float(data.get("expected_gross_profit_bps", 0)),
    )


@app.get("/logs")
def logs(limit: int = Query(100, ge=1, le=1_000)) -> list[dict]:
    return store.tail(limit)


@app.post("/reset", response_model=StateResponse)
def reset() -> dict:
    global last_test_order
    last_test_order = {}
    pending_auto_order.clear()
    state.reset()
    record_event("reset", state.portfolio_dict())
    return state.portfolio_dict()
