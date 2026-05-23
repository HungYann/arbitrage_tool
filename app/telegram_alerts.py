from __future__ import annotations

import json
import logging
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Any


logger = logging.getLogger(__name__)
UTC_PLUS_8 = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    chat_id: str
    enabled: bool = True
    timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> "TelegramConfig":
        return cls(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
            enabled=os.getenv("TELEGRAM_ALERT_ENABLED", "true").lower() == "true",
            timeout_seconds=float(os.getenv("TELEGRAM_TIMEOUT_SECONDS", "10")),
        )


def send_telegram_message(message: str, config: TelegramConfig | None = None) -> dict[str, Any]:
    config = config or TelegramConfig.from_env()
    if not config.enabled:
        return {"ok": False, "skipped": True, "reason": "telegram alerts are disabled"}
    if not config.bot_token:
        return {"ok": False, "skipped": True, "reason": "TELEGRAM_BOT_TOKEN is not configured"}
    if not config.chat_id:
        return {"ok": False, "skipped": True, "reason": "TELEGRAM_CHAT_ID is not configured"}

    url = f"https://api.telegram.org/bot{config.bot_token}/sendMessage"
    payload = urllib.parse.urlencode(
        {
            "chat_id": config.chat_id,
            "text": message,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds, context=create_ssl_context()) as response:
            data = json.loads(response.read().decode("utf-8"))
            return {"ok": bool(data.get("ok")), "status": response.status, "result": data.get("result", {})}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.error("Failed to send Telegram alert: %s", exc)
        return {"ok": False, "error": str(exc)}


def send_telegram_event(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return send_telegram_message(format_telegram_event(event_type, payload))


def format_telegram_event(event_type: str, payload: dict[str, Any]) -> str:
    now = datetime.now(UTC).astimezone(UTC_PLUS_8).strftime("%Y-%m-%d %H:%M:%S UTC+8")
    lines = ["Open Arbitrage Alert", f"Time: {now}", f"Event: {event_type}"]

    quote = payload.get("quote") or {}
    if quote:
        lines.append(
            "Quote: "
            f"bid={quote.get('bid', '')}, "
            f"ask={quote.get('ask', '')}, "
            f"source={quote.get('source', '')}, "
            f"update_id={quote.get('update_id', '')}"
        )

    order = payload.get("order") or payload.get("test_order") or payload.get("cancel") or {}
    if order:
        lines.extend(
            [
                f"Order ID: {order.get('id') or order.get('orderId') or payload.get('order_id', '')}",
                f"Order Status: {order.get('status', '')}",
                f"Symbol: {order.get('symbol') or order.get('ccxt_symbol') or payload.get('symbol', '')}",
                f"Order Price: {order.get('price') or order.get('limit_price') or ''}",
            ]
        )

    return "\n".join(str(line) for line in lines)


def create_ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()
