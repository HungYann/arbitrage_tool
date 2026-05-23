# Open Arbitrage Tool

一个面向 VPS 部署的开源套利工具原型。当前版本默认只做纸面交易和策略计算，不会读取本目录外的交易所密钥，也不会自动下真实订单。

## 目标

- 将默认 30,000 USD 资金拆成 3 份，按价差和收益阈值自动生成买卖决策。
- 捕获每次行情、决策、成交和错误日志，便于在 VPS 上长期运行后回溯。
- 支持 USDT/USD 这类近锚定资产的低价买入、高价卖出逻辑。
- 用 FastAPI 暴露状态、报价、决策、模拟执行、日志查询接口。
- 后续可接入 CCXT、Binance、OKX 等交易所适配器，但实盘交易必须显式开启。

## 策略思路

最简单的固定阈值：

- 当 `USDT/USD <= 0.9994` 时，用 USD 买入 USDT。
- 当 `USDT/USD >= 1.0000` 时，卖出 USDT 换回 USD。
- 单次价差约为万分之五，实际利润还要扣除手续费、滑点和最小下单额。

当前实现已按 `ArbiBot_PRD_v1.1.docx` 加入硬边界和动态梯度：

- 把总资金拆为 `tranche_count` 份，可设置为 1～20 份；默认 30,000 USD 拆成 3 份，每份 10,000 USD。
- `max_buy_price=0.9994` 是买入硬上限；价格高于它时绝不买入。
- `min_sell_price=1.0000` 是卖出硬下限；价格低于它时绝不卖出。
- `0.9996 ~ 0.9999` 是静默区间，系统只记录观察，不做动作。
- `strategy_mode=gradient` 时，买入档位从 `0.9994` 开始按 `grid_step=0.0005` 向下排列；同一档不会重复开仓。
- 当前策略不再使用 `min_buy_price=0.9900` 作为买入熔断；价格跌破该值后仍按剩余网格份数和资金容量判断是否买入。
- 卖出仍会检查扣除手续费和滑点后的 `min_profit_bps`，所以 PRD 的硬价差是毛利润下限，真实成交还要结合费率配置。

## 快速启动

```bash
cd /Users/liuhongyang/Desktop/content/arbitrage_tool
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

打开：

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/health`

## 常用接口

```bash
curl http://127.0.0.1:8000/state
curl -X POST http://127.0.0.1:8000/tick -H 'Content-Type: application/json' -d '{"price":0.9994}'
curl -X POST http://127.0.0.1:8000/tick -H 'Content-Type: application/json' -d '{"price":1.0001,"execute":true}'
curl http://127.0.0.1:8000/logs?limit=20
```

## 可视化后台

项目内置一个 FastapiAdmin 风格的轻量后台：

- `http://127.0.0.1:8000/admin`：运行指标、收益趋势、动作分布、最近操作。服务部署后会自动启动行情监听和策略循环。
- `http://127.0.0.1:8000/admin/config`：参数可视化和编辑。
- `http://127.0.0.1:8000/admin/logs`：操作日志表格。

这不是完整 FastapiAdmin 平台的前后端分离版本，而是沿用其中后台产品形态，在当前 FastAPI 工具里直接提供可视化操作。

后台默认开启登录认证，账号和会话配置来自 `.env`：

```bash
ADMIN_AUTH_ENABLED=true
ADMIN_USERNAME=admin
ADMIN_PASSWORD=replace-with-a-strong-password
ADMIN_SECRET_KEY=replace-with-at-least-32-random-characters
ADMIN_SESSION_TTL_SECONDS=28800
ADMIN_SECURE_COOKIE=false
```

未登录访问 `/admin/api/*` 会返回 `401`，页面访问 `/admin` 会显示登录页。部署到 HTTPS 后应设置 `ADMIN_SECURE_COOKIE=true`，并把 `ADMIN_PASSWORD` 换成 `ADMIN_PASSWORD_HASH`。

## Docker 中间件

项目提供 Docker Compose 编排：

```bash
docker compose --env-file .env up -d --build
```

服务包括：

- `app`：套利工具 FastAPI 服务。
- `redis`：缓存/任务队列/后续会话存储预留中间件。
- `postgres`：后续结构化日志、配置、订单状态落库预留中间件。
- `docs`：Mintlify 文档开发服务，默认开放 `http://127.0.0.1:3000`。

当前版本仍用 JSONL 保存操作日志，Redis/Postgres 先作为可运行的中间件基础设施，方便下一步把日志和会话迁移进去。

## AWS EC2 部署

该工具可以在 AWS EC2 上长期运行，以便实时监控市场行情和自动执行套利策略。

### 前置条件

- AWS 账户和 EC2 实例（推荐 `t3.medium` 或更高规格）
- 实例安装 Docker 和 Docker Compose
- 安全组配置允许 HTTPS（443）和 HTTP（8000）入站

### 部署步骤

1. **连接到 EC2 实例**：

```bash
ssh -i your-key-pair.pem ec2-user@your-instance-public-ip
```

2. **克隆仓库**：

```bash
git clone https://github.com/your-username/arbitrage_tool.git
cd arbitrage_tool
```

3. **配置环境变量**：

```bash
cp .env.example .env
# 编辑 .env，填入实际的 API 密钥、Telegram 配置等
nano .env
```

**重要**：确保以下字段正确配置：
- `BINANCE_API_KEY` 和 `BINANCE_API_SECRET`：Binance 现货交易 API 凭证
- `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID`：接收交易提醒的 Telegram 机器人
- `ADMIN_PASSWORD` 和 `ADMIN_SECRET_KEY`：后台管理员密码和会话密钥
- `TRADING_MODE`：设为 `live` 启用实盘交易，或 `paper` 仅模拟交易
- `BINANCE_LIVE_TRADING`：设为 `true` 才能真实下单（谨慎设置）

4. **启动服务**：

```bash
docker compose --env-file .env up -d --build
```

验证服务运行状态：

```bash
docker compose ps
docker compose logs -f app
```

5. **访问后台**：

打开浏览器访问 `http://your-instance-public-ip:8000/admin`，使用 `.env` 中配置的用户名和密码登录。

### 日志和监控

查看实时日志：

```bash
docker compose logs -f app
```

查询历史操作日志：

```bash
curl http://your-instance-public-ip:8000/logs?limit=100
```

获取当前策略状态：

```bash
curl http://your-instance-public-ip:8000/state
```

### 自动重启

在 EC2 上开启 systemd 服务实现容器自动重启（可选）：

```bash
# 创建 systemd 服务文件
sudo nano /etc/systemd/system/arbitrage.service

[Unit]
Description=Arbitrage Tool Docker Service
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
WorkingDirectory=/home/ec2-user/arbitrage_tool
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target

# 启用并启动服务
sudo systemctl enable arbitrage
sudo systemctl start arbitrage
```

### 安全建议

1. 使用 VPC 安全组限制访问，仅允许 Telegram 和 Binance API 的必要端口
2. 在 HTTPS 反向代理（如 Nginx）后运行应用，并配置 `ADMIN_SECURE_COOKIE=true`
3. 定期备份日志和配置文件
4. 监控 EC2 账单和资源使用，设置告警

## Codex 插件和 MCP

本仓库还包含一个 Codex 插件：

```text
/Users/liuhongyang/Desktop/content/plugins/open-arbitrage-tool
```

插件提供：

- `.codex-plugin/plugin.json`：插件元数据。
- `.mcp.json`：MCP server 配置。
- `skills/open-arbitrage-tool/SKILL.md`：Codex 操作流程。
- `scripts/open_arbitrage_mcp.py`：MCP server。

MCP server 通过 stdio 暴露给 Codex，但只作为控制/数据桥接层。策略执行和状态变更都由正在运行的 FastAPI Web 服务负责。如果服务没跑，`arbitrage_health` 会报告 unavailable，其他查询/交易工具会返回服务不可用错误。

可用 MCP 工具包括：

- `arbitrage_health`
- `arbitrage_get_state`
- `arbitrage_get_balance`
- `arbitrage_get_binance_quote`
- `arbitrage_get_binance_balance`
- `arbitrage_get_config`
- `arbitrage_update_config`
- `arbitrage_evaluate_tick`
- `arbitrage_execute_tick`
- `arbitrage_submit_trade`
- `arbitrage_submit_binance_trade`
- `arbitrage_get_logs`
- `arbitrage_reset`
- `arbitrage_admin_summary`

## Binance 接入

Binance 接入同时支持 REST JSON 和 WebSocket 实时报价：

- `GET /broker/quote`：默认 `source=auto`，优先返回 10 秒内的 WebSocket 缓存报价，没有实时缓存时调用 REST `bookTicker`。
- `GET /broker/quote?source=rest`：只调用 REST `bookTicker` 获取 bid/ask。
- `GET /broker/quote?source=websocket`：只读取 WebSocket 缓存报价；如果尚未收到报价，会返回 `warming_up`。
- Binance `<symbol>@bookTicker` WebSocket 流会随服务启动自动运行。
- `GET /broker/ws/status`：查看流状态、最新报价和错误。
- `GET /broker/balance`：签名查询账户资产。
- 自动交易循环会优先使用 WebSocket 实时 bid/ask，缓存不可用时回退 REST，运行策略后必要时提交现货限价单。

Binance 现货 WebSocket 官方主域名是 `wss://stream.binance.com:9443` 或 `wss://stream.binance.com:443`，直接访问格式为 `/ws/<streamName>`，组合 stream 格式为 `/stream?streams=<streamName1>/<streamName2>`，且交易对必须小写。`wss://data-stream.binance.vision` 只能订阅市场行情，不能获取账户信息。当前服务只把 WebSocket 用于公开行情，账户余额和下单仍走 Binance REST。

本工具的业务口径是 `USDT/USD`：`USD` 是支付单位和记账单位，买入时用 USD 换 USDT，卖出时把 USDT 换回 USD。默认订阅 `USDTUSD`，并直接把 Binance bid/ask 作为策略价格。若你的 Binance 环境没有直接的 USD 现货市场，才应显式改成代理市场，并同步确认实际支付资产。

WebSocket 连接会自动处理 PING/PONG；服务也会在 24 小时连接上限前主动重连，并在收到 `serverShutdown` 事件后尽快重连。

环境变量：

```bash
BINANCE_SYMBOL=USDTUSD
BINANCE_BASE_ASSET=USDT
BINANCE_QUOTE_ASSET=USD
BINANCE_INVERT_PRICE=false
BINANCE_REST_URL=https://api.binance.com
BINANCE_WS_URL=wss://data-stream.binance.vision/ws
BINANCE_WS_ENABLED=false
BINANCE_WS_MAX_CONNECTION_SECONDS=85500
BINANCE_WS_MESSAGE_TIMEOUT_SECONDS=15
BINANCE_LIVE_TRADING=false
BINANCE_API_KEY=
BINANCE_API_SECRET=
CCXT_ENABLED=true
CCXT_EXCHANGE_ID=binance
CCXT_SYMBOL=USDT/USD
CCXT_TIMEOUT_MS=10000
```

如果必须用反向代理市场，例如 `USDCUSDT`，可以显式设置：

```bash
BINANCE_SYMBOL=USDCUSDT
BINANCE_BASE_ASSET=USDT
BINANCE_QUOTE_ASSET=USDC
BINANCE_INVERT_PRICE=true
```

这种模式只是行情和执行代理，不应混淆为策略的默认 USD 记账口径。

## CCXT 适配

普通 `ccxt` 包用于 REST 适配：`fetch_ticker`、`fetch_balance` 和实盘订单提交。实时行情仍使用 Binance WebSocket，因为普通 CCXT 不提供免费 WebSocket；如果要把 WebSocket 也统一到 CCXT，需要另行接入 CCXT Pro 或继续保留当前 stream 实现。

默认配置使用 Binance 主站：`CCXT_EXCHANGE_ID=binance`。业务口径仍是 `USDT/USD` 和 USD 支付单位，所以 `CCXT_SYMBOL` 默认保留为 `USDT/USD`。如果主站账户实际使用的现货市场不是直接 USD 交易对，必须显式修改 `CCXT_SYMBOL`，并先在 paper 模式检查 `/broker/quote`、`/broker/balance` 与 Admin 实时行情。

`BINANCE_LIVE_TRADING=false` 时，`/broker/trade` 只返回 `SIMULATED` 订单并更新 paper 状态。只有显式设为 `true` 才会发真实 Binance 现货市价单。

## 安全原则

- 默认 `TRADING_MODE=paper`，只做模拟成交。
- 实盘模式应单独实现交易所 Broker，并要求人工设置 `TRADING_MODE=live`。
- API key 不要写进代码，使用环境变量或 VPS 的 secret 管理。
- 每次下单前必须检查余额、手续费、滑点、最小下单额、最大单笔金额和当日亏损上限。
- 任何异常都应记录日志，不能静默失败。

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

MIT License © 2024 Andrew Liu
