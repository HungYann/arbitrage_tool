from __future__ import annotations

import html
import secrets
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from .auth import (
    CAPTCHA_COOKIE,
    auth_status,
    clear_admin_cookie,
    clear_captcha_cookie,
    generate_captcha_code,
    require_admin_api,
    set_admin_cookie,
    set_captcha_cookie,
    validate_admin_captcha,
    verify_admin_credentials,
)
from .broker import BinanceBookTickerStream
from .schemas import StrategyConfigPayload
from .store import JsonlEventStore, RuntimeState
from .strategy import StrategyConfig


def create_admin_router(state: RuntimeState, store: JsonlEventStore, quote_stream: BinanceBookTickerStream | None = None) -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["admin"])

    @router.get("", response_class=HTMLResponse, include_in_schema=False)
    def dashboard(request: Request) -> Response:
        if not is_admin_authenticated(request):
            return _login_response("Please sign in to continue.")
        return HTMLResponse(_admin_shell("dashboard"))

    @router.get("/logs", response_class=HTMLResponse, include_in_schema=False)
    def logs_page(request: Request) -> Response:
        if not is_admin_authenticated(request):
            return _login_response("Please sign in to continue.")
        return HTMLResponse(_admin_shell("logs"))

    @router.get("/config", response_class=HTMLResponse, include_in_schema=False)
    def config_page(request: Request) -> Response:
        if not is_admin_authenticated(request):
            return _login_response("Please sign in to continue.")
        return HTMLResponse(_admin_shell("config"))

    @router.get("/login", response_class=HTMLResponse, include_in_schema=False)
    def login_page() -> Response:
        return _login_response("Enter your admin password.")

    @router.get("/captcha", include_in_schema=False)
    def captcha() -> Response:
        code = generate_captcha_code()
        response = Response(
            content=_captcha_svg(code),
            media_type="image/svg+xml",
            headers={"Cache-Control": "no-store, max-age=0"},
        )
        set_captcha_cookie(response, code)
        return response

    @router.post("/login", include_in_schema=False)
    async def login(request: Request) -> Response:
        body = await request.json()
        username = str(body.get("username", ""))
        password = str(body.get("password", ""))
        captcha_answer = str(body.get("captcha", ""))
        captcha_token = request.cookies.get(CAPTCHA_COOKIE)
        if not validate_admin_captcha(captcha_answer, captcha_token):
            store.append("admin_login_failed", {"username": username, "reason": "invalid_captcha"})
            response = JSONResponse(
                {"detail": "Invalid or expired verification code.", "reason": "invalid_captcha"},
                status_code=401,
            )
            clear_admin_cookie(response)
            clear_captcha_cookie(response)
            return response
        if not verify_admin_credentials(username, password):
            store.append("admin_login_failed", {"username": username, "reason": "invalid_credentials"})
            response = JSONResponse(
                {"detail": "Invalid username or password.", "reason": "invalid_credentials"},
                status_code=401,
            )
            clear_admin_cookie(response)
            clear_captcha_cookie(response)
            return response
        response = JSONResponse({"ok": True})
        set_admin_cookie(response, username)
        clear_captcha_cookie(response)
        store.append("admin_login", {"username": username})
        return response

    @router.post("/logout", include_in_schema=False)
    def logout() -> Response:
        response = JSONResponse({"ok": True})
        clear_admin_cookie(response)
        clear_captcha_cookie(response)
        return response

    @router.get("/api/auth", dependencies=[Depends(require_admin_api)])
    def admin_auth(request: Request) -> dict[str, Any]:
        return auth_status(request)

    @router.get("/api/summary", dependencies=[Depends(require_admin_api)])
    def admin_summary(limit: int = Query(500, ge=1, le=5_000)) -> dict[str, Any]:
        events = store.tail(limit)
        return build_admin_summary(state, events)

    @router.get("/api/logs", dependencies=[Depends(require_admin_api)])
    def admin_logs(limit: int = Query(200, ge=1, le=2_000)) -> dict[str, Any]:
        return {"events": store.tail(limit)}

    @router.get("/api/realtime", dependencies=[Depends(require_admin_api)])
    def admin_realtime(limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
        stream_status = quote_stream.status() if quote_stream else None
        return {
            "server_time_utc8": utc8_now_iso(),
            "quote_stream": with_utc8_quote_time(stream_status),
            "recent_events": store.tail(limit),
        }

    @router.get("/api/config", dependencies=[Depends(require_admin_api)])
    def admin_config() -> dict[str, Any]:
        return state.config_dict()

    @router.put("/api/config", dependencies=[Depends(require_admin_api)])
    def admin_update_config(payload: StrategyConfigPayload = Body(...)) -> dict[str, Any]:
        state.config = StrategyConfig(**payload.model_dump())
        state.reset()
        store.append("config_updated", state.config_dict())
        return {"config": state.config_dict(), "state": state.portfolio_dict()}

    return router


def is_admin_authenticated(request: Request) -> bool:
    return auth_status(request)["authenticated"]


def utc8_now_iso() -> str:
    return datetime.now(UTC).astimezone(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def with_utc8_quote_time(stream_status: dict[str, Any] | None) -> dict[str, Any] | None:
    if not stream_status:
        return None
    latest = stream_status.get("latest")
    if isinstance(latest, dict):
        latest["received_at_utc8"] = to_utc8_iso(str(latest.get("received_at", "")))
    return stream_status


def to_utc8_iso(value: str) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    except ValueError:
        return None


def _login_response(message: str = "") -> HTMLResponse:
    response = HTMLResponse(_login_shell(message))
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    clear_admin_cookie(response)
    return response


def _login_shell(message: str = "") -> str:
    safe_message = html.escape(message)
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Open Arbitrage Admin Login</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f8f7;
      --panel: #ffffff;
      --text: #111827;
      --muted: #64748b;
      --line: #d9e2df;
      --primary: #0f766e;
      --danger: #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
      background: var(--bg);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    .panel {
      width: min(420px, 100%);
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 24px;
      box-shadow: 0 12px 30px rgba(15, 23, 42, 0.08);
    }
    h1 { margin: 0; font-size: 24px; line-height: 1.2; }
    .sub { color: var(--muted); margin: 8px 0 22px; font-size: 14px; }
    label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 6px; }
    input {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 11px;
      font-size: 15px;
      margin-bottom: 14px;
    }
    button {
      width: 100%;
      border: 1px solid var(--primary);
      background: var(--primary);
      color: #ffffff;
      border-radius: 8px;
      padding: 10px 12px;
      cursor: pointer;
      font-weight: 700;
      font-size: 15px;
    }
    .captcha-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 134px;
      gap: 10px;
      align-items: start;
    }
    .captcha-image {
      width: 134px;
      height: 42px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #eef5f3;
      object-fit: cover;
      cursor: pointer;
    }
    .captcha-hint {
      color: var(--muted);
      font-size: 12px;
      margin: -8px 0 14px;
    }
    .message { color: var(--muted); min-height: 20px; margin-bottom: 12px; font-size: 13px; }
    .error { color: var(--danger); min-height: 20px; margin-top: 12px; font-size: 13px; }
    @media (max-width: 420px) {
      .captcha-row { grid-template-columns: 1fr; }
      .captcha-image { width: 100%; }
    }
  </style>
</head>
<body>
  <section class="panel">
    <h1>Open Arbitrage Admin</h1>
    <div class="sub">Sign in to view prices, logs, and trading parameters.</div>
    <div class="message">__LOGIN_MESSAGE__</div>
    <form id="login-form">
      <label for="username">Username</label>
      <input id="username" name="username" autocomplete="username" required />
      <label for="password">Password</label>
      <input id="password" name="password" type="password" autocomplete="current-password" required />
      <label for="captcha">Verification code</label>
      <div class="captcha-row">
      <input id="captcha" name="captcha" autocomplete="off" inputmode="text" maxlength="8" autocapitalize="characters" required />
        <img id="captcha-image" class="captcha-image" src="/admin/captcha" alt="Verification code" title="Click to refresh" draggable="false" />
      </div>
      <div class="captcha-hint">Click the image to refresh.</div>
      <button type="submit">Sign In</button>
      <div id="error" class="error"></div>
    </form>
  </section>
  <script>
    document.getElementById('login-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const error = document.getElementById('error');
      error.textContent = '';
      const form = new FormData(event.target);
      const response = await fetch('/admin/login', {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: form.get('username'),
          password: form.get('password'),
          captcha: String(form.get('captcha') || '').toUpperCase().trim()
        })
      });
      if (!response.ok) {
        let message = 'Invalid username, password, or verification code.';
        try {
          const data = await response.json();
          if (data.detail) message = data.detail;
        } catch (error) {
          message = 'Login failed. Please refresh the verification code and try again.';
        }
        refreshCaptcha();
        document.getElementById('captcha').value = '';
        error.textContent = message;
        return;
      }
      window.location.href = '/admin';
    });
    function refreshCaptcha() {
      document.getElementById('captcha-image').src = '/admin/captcha?t=' + Date.now();
    }
    document.getElementById('captcha').addEventListener('input', (event) => {
      event.target.value = event.target.value.toUpperCase().replace(/\s/g, '');
    });
    document.getElementById('captcha-image').addEventListener('click', refreshCaptcha);
  </script>
</body>
</html>""".replace("__LOGIN_MESSAGE__", safe_message)


def _captcha_svg(code: str) -> str:
    chars = []
    for index, char in enumerate(code):
        x = 19 + index * 24
        y = 31
        chars.append(
            f'<text x="{x}" y="{y}" font-size="27" font-weight="800" '
            f'font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" '
            f'fill="#123a35">{html.escape(char)}</text>'
        )
    lines = []
    for _ in range(1):
        x1 = secrets.randbelow(132)
        y1 = secrets.randbelow(42)
        x2 = secrets.randbelow(132)
        y2 = secrets.randbelow(42)
        color = ["#0f766e", "#1d4ed8", "#64748b"][secrets.randbelow(3)]
        lines.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.2" opacity="0.45"/>')
    dots = []
    for _ in range(6):
        cx = secrets.randbelow(132)
        cy = secrets.randbelow(42)
        dots.append(f'<circle cx="{cx}" cy="{cy}" r="1" fill="#64748b" opacity="0.45"/>')
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="134" height="42" viewBox="0 0 134 42" role="img">'
        '<rect width="134" height="42" rx="8" fill="#eef5f3"/>'
        + "".join(lines)
        + "".join(chars)
        + "".join(dots)
        + "</svg>"
    )


def build_admin_summary(state: RuntimeState, events: list[dict[str, Any]]) -> dict[str, Any]:
    action_counts: Counter[str] = Counter()
    event_counts: Counter[str] = Counter()
    executed_count = 0
    profit_points = []

    for index, event in enumerate(events):
        event_type = event.get("type", "unknown")
        event_counts[event_type] += 1
        payload = event.get("payload") or {}
        decision = payload.get("decision") or {}
        action = decision.get("action")
        if action:
            action_counts[action] += 1
        if decision.get("executed"):
            executed_count += 1
        snapshot = payload.get("state") or {}
        if "realized_profit_usd" in snapshot:
            profit_points.append(
                {
                    "index": index,
                    "ts": event.get("ts"),
                    "value": snapshot.get("realized_profit_usd", 0),
                }
            )

    portfolio = state.portfolio_dict()
    config = state.config_dict()
    return {
        "config": config,
        "portfolio": portfolio,
        "metrics": {
            "events": len(events),
            "ticks": event_counts.get("tick", 0),
            "buys": action_counts.get("buy", 0),
            "sells": action_counts.get("sell", 0),
            "holds": action_counts.get("hold", 0),
            "executed": executed_count,
            "open_tranches": len(portfolio["open_tranches"]),
            "realized_profit_usd": portfolio["realized_profit_usd"],
            "usd_available": portfolio["usd_available"],
            "usdt_available": portfolio["usdt_available"],
            "tranche_size_usd": config["total_capital_usd"] / config["tranche_count"],
        },
        "event_counts": dict(event_counts),
        "action_counts": dict(action_counts),
        "profit_points": profit_points[-80:],
        "recent_events": events[-20:],
    }


def _admin_shell(active: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Open Arbitrage Admin</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f8f7;
      --panel: #ffffff;
      --text: #111827;
      --muted: #64748b;
      --line: #d9e2df;
      --primary: #0f766e;
      --primary-weak: #d9f3ee;
      --danger: #b42318;
      --buy: #0f766e;
      --sell: #1d4ed8;
      --hold: #7c3aed;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
      letter-spacing: 0;
    }}
    .layout {{
      display: grid;
      grid-template-columns: 244px minmax(0, 1fr);
      min-height: 100vh;
    }}
    aside {{
      background: #0b1f1d;
      color: #d9f3ee;
      padding: 22px 16px;
    }}
    .brand {{
      font-weight: 760;
      font-size: 18px;
      line-height: 1.25;
      margin: 0 0 24px;
    }}
    nav a {{
      display: flex;
      align-items: center;
      gap: 10px;
      min-height: 40px;
      padding: 9px 11px;
      border-radius: 8px;
      color: #b9d8d2;
      text-decoration: none;
      font-size: 14px;
      margin-bottom: 5px;
    }}
    nav a.active, nav a:hover {{
      background: #123a35;
      color: #ffffff;
    }}
    main {{ padding: 24px; }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 18px;
      margin-bottom: 22px;
    }}
    h1 {{
      margin: 0;
      font-size: 24px;
      line-height: 1.2;
    }}
    .sub {{ color: var(--muted); margin-top: 6px; font-size: 14px; }}
    .button {{
      border: 1px solid var(--primary);
      background: var(--primary);
      color: #fff;
      border-radius: 8px;
      padding: 9px 12px;
      cursor: pointer;
      font-weight: 650;
      font-size: 14px;
    }}
    .button.secondary {{
      color: var(--primary);
      background: #fff;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    }}
	    .metric .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; }}
	    .metric .value {{ font-size: 24px; font-weight: 760; margin-top: 8px; }}
	    .metric .hint {{ color: var(--muted); font-size: 12px; margin-top: 6px; overflow-wrap: anywhere; }}
	    .two {{
	      display: grid;
	      grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
	      gap: 16px;
	    }}
	    .quote-grid {{
	      display: grid;
	      grid-template-columns: repeat(4, minmax(0, 1fr));
	      gap: 12px;
	      margin-top: 12px;
	    }}
	    .quote-strip {{
	      display: grid;
	      grid-template-columns: repeat(3, minmax(0, 1fr));
	      gap: 10px;
	      margin-top: 12px;
	      padding: 12px;
	      border: 1px solid var(--line);
	      border-radius: 8px;
	      background: #f8fbfa;
	    }}
	    .quote-strip span {{
	      display: block;
	      color: var(--muted);
	      font-size: 12px;
	      margin-bottom: 4px;
	    }}
	    .quote-strip strong {{
	      color: var(--text);
	      font-size: 14px;
	      overflow-wrap: anywhere;
	    }}
	    .panel-head {{
	      display: flex;
	      align-items: center;
	      justify-content: space-between;
	      gap: 12px;
	      margin-bottom: 10px;
	    }}
	    .panel-head h2 {{ margin: 0; }}
	    .toolbar {{ display: flex; gap: 8px; flex-wrap: wrap; }}
	    .status-pill {{
	      display: inline-flex;
	      align-items: center;
	      min-height: 26px;
	      border-radius: 999px;
	      padding: 4px 9px;
	      font-size: 12px;
	      font-weight: 700;
	      background: #eef5f3;
	      color: #31524e;
	    }}
	    .status-pill.live {{ background: #dcfce7; color: #166534; }}
	    .status-pill.waiting {{ background: #fef3c7; color: #92400e; }}
	    .status-pill.error {{ background: #fee2e2; color: var(--danger); }}
	    .kv {{
	      display: grid;
	      grid-template-columns: repeat(3, minmax(0, 1fr));
	      gap: 10px;
	      color: var(--muted);
	      font-size: 13px;
	    }}
	    .kv strong {{ display: block; color: var(--text); font-size: 14px; margin-top: 3px; overflow-wrap: anywhere; }}
    .bar-row {{
      display: grid;
      grid-template-columns: 70px minmax(0, 1fr) 48px;
      align-items: center;
      gap: 10px;
      margin: 11px 0;
      font-size: 13px;
    }}
    .bar-track {{ background: #edf2f1; height: 10px; border-radius: 999px; overflow: hidden; }}
    .bar-fill {{ height: 100%; border-radius: 999px; background: var(--primary); }}
    .bar-fill.buy {{ background: var(--buy); }}
    .bar-fill.sell {{ background: var(--sell); }}
    .bar-fill.hold {{ background: var(--hold); }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 10px 8px;
      text-align: left;
      vertical-align: top;
    }}
    th {{ color: var(--muted); font-weight: 700; }}
    code {{
      background: #eef5f3;
      border-radius: 6px;
      padding: 2px 5px;
      font-size: 12px;
    }}
    .form-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }}
    label {{ display: block; font-size: 12px; color: var(--muted); margin-bottom: 5px; }}
    input {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 9px 10px;
      font-size: 14px;
    }}
    .notice {{
      background: var(--primary-weak);
      border: 1px solid #9eddd3;
      border-radius: 8px;
      padding: 12px;
      color: #134e4a;
      font-size: 14px;
      margin-bottom: 14px;
    }}
    .chart {{
      width: 100%;
      height: 180px;
      display: block;
    }}
    .empty {{ color: var(--muted); padding: 14px 0; }}
	    @media (max-width: 980px) {{
	      .layout {{ grid-template-columns: 1fr; }}
	      aside {{ position: static; }}
	      .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
	      .quote-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
	      .quote-strip {{ grid-template-columns: 1fr; }}
	      .two {{ grid-template-columns: 1fr; }}
	      .kv {{ grid-template-columns: 1fr; }}
	      .form-grid {{ grid-template-columns: 1fr; }}
	    }}
  </style>
</head>
<body data-active="{active}">
  <div class="layout">
    <aside>
      <div class="brand">Open Arbitrage<br/>Admin</div>
      <nav>
        <a href="/admin" data-page="dashboard">Dashboard</a>
        <a href="/admin/config" data-page="config">Parameters</a>
        <a href="/admin/logs" data-page="logs">Operation Logs</a>
        <a href="/docs">FastAPI Docs</a>
        <a href="#" onclick="logoutAdmin(); return false;">Sign Out</a>
      </nav>
    </aside>
    <main>
      <header>
        <div>
          <h1 id="page-title">Dashboard</h1>
          <div class="sub">Paper-trading operations, strategy parameters, and JSONL audit events.</div>
        </div>
        <button class="button secondary" onclick="manualRefresh()">Refresh</button>
      </header>
      <section id="content"></section>
    </main>
  </div>
  <script>
    const active = document.body.dataset.active;
    document.querySelectorAll('nav a[data-page]').forEach((node) => {{
      if (node.dataset.page === active) node.classList.add('active');
    }});

    const fmt = new Intl.NumberFormat('en-US', {{ maximumFractionDigits: 6 }});
    const money = new Intl.NumberFormat('en-US', {{ style: 'currency', currency: 'USD', maximumFractionDigits: 4 }});

    async function fetchJson(url, options) {{
      const res = await fetch(url, options);
      if (res.status === 401) {{
        await forceAdminLogout();
        throw new Error('Admin session expired. Please sign in again.');
      }}
      if (!res.ok) throw new Error(await res.text());
      return await res.json();
    }}

    async function forceAdminLogout() {{
      try {{
        await fetch('/admin/logout', {{ method: 'POST' }});
      }} finally {{
        window.location.replace('/admin/login');
      }}
    }}

    function showPopup(message) {{
      window.alert(message);
    }}

	    function metric(label, value) {{
	      return `<div class="panel metric"><div class="label">${{label}}</div><div class="value">${{value}}</div></div>`;
	    }}

	    function quoteMetric(label, value, hint = '') {{
	      return `<div class="panel metric"><div class="label">${{label}}</div><div class="value">${{value}}</div>${{hint ? `<div class="hint">${{hint}}</div>` : ''}}</div>`;
	    }}

	    function quoteStatus(stream) {{
	      if (!stream) return '<span class="status-pill error">Unavailable</span>';
	      if (stream.last_error) return '<span class="status-pill error">Error</span>';
	      if (stream.running && stream.latest) return '<span class="status-pill live">Live</span>';
	      if (stream.running) return '<span class="status-pill waiting">Warming up</span>';
	      return '<span class="status-pill">Stopped</span>';
	    }}

	    function quotePanel(stream, serverTimeUtc8) {{
	      const latest = stream?.latest || null;
	      const bid = latest ? fmt.format(latest.bid) : '-';
	      const ask = latest ? fmt.format(latest.ask) : '-';
	      const mid = latest ? fmt.format(latest.mid) : '-';
	      const source = latest?.source || '-';
	      const updated = latest?.received_at_utc8 || latest?.received_at || '-';
	      const raw = latest?.raw_bid != null ? `raw ${{fmt.format(latest.raw_bid)}} / ${{fmt.format(latest.raw_ask)}}` : '';
	      const latestQuote = latest ? `${{latest.base_asset}}/${{latest.quote_asset}} bid ${{bid}} · ask ${{ask}} · mid ${{mid}}` : '-';
	      return `<section class="panel" style="margin-bottom:16px">
	        <div class="panel-head">
	          <div>
	            <h2>Realtime Binance Quote</h2>
	            <div class="sub">${{stream?.symbol || '-'}} · ${{stream?.stream || '-'}} · ${{stream?.url || '-'}}</div>
	          </div>
	          <div class="toolbar">
	            ${{quoteStatus(stream)}}
	            <button class="button secondary" onclick="createTestOrder()">Test Order</button>
	            <button class="button secondary" onclick="cancelTestOrder()">Cancel Test</button>
	          </div>
	        </div>
	        <div class="quote-strip">
	          <div><span>UTC+8 Time</span><strong>${{serverTimeUtc8 || '-'}}</strong></div>
	          <div><span>Latest Quote</span><strong>${{latestQuote}}</strong></div>
	          <div><span>Quote Updated UTC+8</span><strong>${{updated}}</strong></div>
	        </div>
	        <div class="quote-grid">
	          ${{quoteMetric('Bid', bid, latest ? `${{latest.base_asset}}/${{latest.quote_asset}}` : '')}}
	          ${{quoteMetric('Ask', ask, latest ? `${{latest.base_asset}}/${{latest.quote_asset}}` : '')}}
	          ${{quoteMetric('Mid', mid, raw)}}
	          ${{quoteMetric('Source', source, updated)}}
	        </div>
	        <div class="kv" style="margin-top:12px">
	          <div>Update ID<strong>${{latest?.update_id ?? '-'}}</strong></div>
	          <div>Raw Symbol<strong>${{latest?.raw_symbol || '-'}}</strong></div>
	          <div>Last Error<strong>${{stream?.last_error || '-'}}</strong></div>
	        </div>
	      </section>`;
	    }}

    function bars(counts) {{
      const max = Math.max(1, ...Object.values(counts));
      return ['buy', 'sell', 'hold'].map((key) => {{
        const value = counts[key] || 0;
        const width = Math.max(2, value / max * 100);
        return `<div class="bar-row"><span>${{key}}</span><div class="bar-track"><div class="bar-fill ${{key}}" style="width:${{width}}%"></div></div><strong>${{value}}</strong></div>`;
      }}).join('');
    }}

    function chart(points) {{
      if (!points.length) return '<div class="empty">No profit points yet.</div>';
      const values = points.map((p) => Number(p.value || 0));
      const min = Math.min(...values);
      const max = Math.max(...values);
      const spread = max - min || 1;
      const coords = values.map((value, index) => {{
        const x = values.length === 1 ? 0 : index / (values.length - 1) * 100;
        const y = 100 - ((value - min) / spread * 76 + 12);
        return `${{x}},${{y}}`;
      }}).join(' ');
      return `<svg class="chart" viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="Realized profit trend">
        <polyline points="${{coords}}" fill="none" stroke="#0f766e" stroke-width="2.6" vector-effect="non-scaling-stroke" />
      </svg>`;
    }}

	    function eventRows(events) {{
	      if (!events.length) return '<tr><td colspan="5" class="empty">No events yet.</td></tr>';
	      return events.slice().reverse().map((event) => {{
	        const payload = event.payload || {{}};
	        const decision = payload.decision || {{}};
	        const request = payload.request || {{}};
	        const quote = payload.quote || {{}};
	        const price = request.price ?? decision.price ?? quote.mid ?? '-';
	        return `<tr>
	          <td>${{event.ts || ''}}</td>
	          <td><code>${{event.type || 'unknown'}}</code></td>
	          <td>${{decision.action || '-'}}</td>
	          <td>${{price}}</td>
	          <td>${{decision.reason || quote.source || JSON.stringify(payload).slice(0, 180)}}</td>
	        </tr>`;
	      }}).join('');
	    }}

	    async function renderDashboard() {{
	      document.getElementById('page-title').textContent = 'Dashboard';
	      const [data, realtime] = await Promise.all([
	        fetchJson('/admin/api/summary'),
	        fetchJson('/admin/api/realtime?limit=20')
	      ]);
	      const m = data.metrics;
	      document.getElementById('content').innerHTML = `
	        ${{quotePanel(realtime.quote_stream, realtime.server_time_utc8)}}
	        <div class="grid">
	          ${{metric('USD Available', money.format(m.usd_available))}}
	          ${{metric('USDT Available', fmt.format(m.usdt_available))}}
          ${{metric('Realized Profit', money.format(m.realized_profit_usd))}}
          ${{metric('Open Tranches', fmt.format(m.open_tranches))}}
        </div>
        <div class="two">
          <section class="panel">
            <h2>Profit Trend</h2>
            ${{chart(data.profit_points)}}
          </section>
          <section class="panel">
            <h2>Action Mix</h2>
            ${{bars(data.action_counts)}}
          </section>
        </div>
        <section class="panel" style="margin-top:16px">
          <h2>Recent Operations</h2>
          <table><thead><tr><th>Time</th><th>Type</th><th>Action</th><th>Price</th><th>Reason</th></tr></thead><tbody>${{eventRows(data.recent_events)}}</tbody></table>
        </section>`;
    }}

	    async function renderLogs() {{
	      document.getElementById('page-title').textContent = 'Operation Logs';
	      const [data, realtime] = await Promise.all([
	        fetchJson('/admin/api/logs?limit=500'),
	        fetchJson('/admin/api/realtime?limit=20')
	      ]);
	      document.getElementById('content').innerHTML = `
	        ${{quotePanel(realtime.quote_stream, realtime.server_time_utc8)}}
	        <section class="panel">
	          <h2>JSONL Events</h2>
	          <table><thead><tr><th>Time</th><th>Type</th><th>Action</th><th>Price</th><th>Reason / Payload</th></tr></thead><tbody>${{eventRows(data.events)}}</tbody></table>
	        </section>`;
	    }}

    async function renderConfig() {{
      document.getElementById('page-title').textContent = 'Parameters';
      const config = await fetchJson('/admin/api/config');
      const editableFields = [
        ['total_capital_usd', 'Total Capital USD'],
        ['tranche_count', 'Tranche Count']
      ];
      const fields = editableFields.map(([key, label]) => `
        <div>
          <label for="${{key}}">${{label}}</label>
          <input id="${{key}}" name="${{key}}" type="number" step="${{key === 'tranche_count' ? '1' : 'any'}}" min="${{key === 'tranche_count' ? '1' : '500'}}" max="${{key === 'tranche_count' ? '20' : '200000'}}" value="${{config[key]}}">
        </div>`).join('');
      document.getElementById('content').innerHTML = `
        <div class="notice">Only total capital and tranche count are editable here. Saving resets the current portfolio and records a config_updated event.</div>
        <section class="panel">
          <form id="config-form">
            <div class="form-grid">${{fields}}</div>
            <div style="margin-top:14px"><button class="button" type="submit">Save Parameters</button></div>
          </form>
        </section>`;
      document.getElementById('config-form').addEventListener('submit', saveConfig);
    }}

	    async function saveConfig(event) {{
      event.preventDefault();
      try {{
        const current = await fetchJson('/admin/api/config');
        const changes = Object.fromEntries([...new FormData(event.target).entries()].map(([k, v]) => [k, Number(v)]));
        const payload = {{ ...current, ...changes, max_open_tranches: changes.tranche_count }};
        await fetchJson('/admin/api/config', {{
          method: 'PUT',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(payload)
        }});
        await renderConfig();
        showPopup('Parameters saved.');
      }} catch (error) {{
        showPopup(`Failed to save parameters: ${{error.message}}`);
      }}
	    }}

    function summarizeOrder(data) {{
      const order = data?.test_order?.order || data?.cancel || data?.order || {{}};
      const orderId = data?.test_order?.id || data?.order_id || order.id || order.orderId || '-';
      const status = order.status || '-';
      const price = data?.test_order?.limit_price || order.price || '-';
      return `Order ID: ${{orderId}}\nStatus: ${{status}}\nPrice: ${{price}}`;
    }}

    async function createTestOrder() {{
      try {{
        const data = await fetchJson('/broker/test-order?notional_usd=10&price_multiplier=0.9999', {{ method: 'POST' }});
        await loadAll();
        showPopup(`Test limit order created.\n${{summarizeOrder(data)}}\n\nCheck Binance open orders, then click Cancel Test.`);
      }} catch (error) {{
        showPopup(`Failed to create test order: ${{error.message}}`);
      }}
    }}

    async function cancelTestOrder() {{
      try {{
        const data = await fetchJson('/broker/test-order/cancel', {{ method: 'POST' }});
        await loadAll();
        showPopup(`Test order cancel requested.\n${{summarizeOrder(data)}}`);
      }} catch (error) {{
        showPopup(`Failed to cancel test order: ${{error.message}}`);
      }}
    }}

    async function manualRefresh() {{
      try {{
        await loadAll();
        showPopup('Page refreshed.');
      }} catch (error) {{
        showPopup(`Refresh failed: ${{error.message}}`);
      }}
    }}

    async function logoutAdmin() {{
      await fetch('/admin/logout', {{ method: 'POST' }});
      window.location.href = '/admin/login';
    }}

    async function loadAll() {{
      if (active === 'logs') return renderLogs();
      if (active === 'config') return renderConfig();
      return renderDashboard();
    }}

	    loadAll().catch((error) => {{
	      document.getElementById('content').innerHTML = `<div class="panel"><strong>Failed to load admin data</strong><p>${{error.message}}</p></div>`;
	    }});
	    if (active !== 'config') {{
	      window.setInterval(() => {{
	        loadAll().catch((error) => console.error(error));
	      }}, 3000);
	    }}
	  </script>
</body>
</html>"""
