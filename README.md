# Open Arbitrage Tool

<div align="center">

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Documentation](https://img.shields.io/badge/docs-gitHub%20Pages-blue)](https://hungyann.github.io/arbitrage_tool/)
[![CI/CD Pipeline](https://img.shields.io/badge/CI%2FCD-GitHub%20Actions-brightgreen)](https://github.com/HungYann/arbitrage_tool/actions)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Node.js 18+](https://img.shields.io/badge/node-18+-green.svg)](https://nodejs.org/)
[![Docker](https://img.shields.io/badge/docker-supported-blue?logo=docker)](Dockerfile)

[![Code Quality](https://img.shields.io/badge/code%20quality-A-brightgreen)](https://github.com/HungYann/arbitrage_tool/actions)
[![Test Coverage](https://img.shields.io/badge/test%20coverage-pytest-blue)](https://github.com/HungYann/arbitrage_tool/tree/main/tests)
[![Security Scans](https://img.shields.io/badge/security-bandit%20%26%20safety-orange)](https://github.com/HungYann/arbitrage_tool/actions)
[![Latest Release](https://img.shields.io/badge/release-v0.1.0-blue)](https://github.com/HungYann/arbitrage_tool/releases)

</div>

**完全开源化、自动化、安全的生产级套利交易系统**

支持 Binance 等交易所的自动化套利交易，具备企业级后台管理界面、实时行情监控、策略管理和订单追踪能力。面向 VPS 长期部署运行，可按需配置纸面交易或真实下单模式。

## 核心功能

**自动化交易**
- 按价差和收益阈值自动生成买卖决策，支持梯度网格策略
- 将资金拆成多份分批交易，降低单次风险
- 支持 USDT/USD 等近锚定资产的低买高卖套利逻辑
- 集成 Binance REST + WebSocket 实时行情和交易能力

**后台管理界面**
- 可视化仪表板：实时行情、策略状态、收益趋势、操作分布
- 参数管理：动态调整交易策略和风险控制参数
- 操作日志：追踪所有交易、决策和系统事件
- 登录认证：内置账户和会话管理，支持密码和密钥认证

**企业级可靠性**
- 完整的日志系统：捕获行情、决策、成交和错误信息
- 纸面交易模式：安全测试策略，无真实资金风险
- 实盘交易模式：生产级风险控制，手续费和滑点计算
- 长期运行能力：在 VPS 上稳定运行，自动重启机制
- Docker 容器化：Redis、PostgreSQL 等中间件支持

**开发友好**
- FastAPI RESTful 接口：状态查询、报价获取、交易执行、日志查询
- OpenAPI 文档：自动生成的 API 文档和在线测试
- Codex 插件和 MCP：与 Claude Code 集成，支持编程协助
- 详尽的文档：包括本地开发、AWS 部署、配置指南

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

## 容器化部署

### Docker Compose 本地开发

快速启动完整的开发环境：

```bash
# 克隆仓库
git clone https://github.com/HungYann/arbitrage_tool.git
cd arbitrage_tool

# 创建并配置环境变量
cp .env.example .env
nano .env  # 编辑配置（API密钥、数据库密码等）

# 启动所有服务（应用、Redis、PostgreSQL、文档）
docker compose up -d --build

# 查看服务状态
docker compose ps

# 查看应用日志
docker compose logs -f app
```

服务访问地址：
- **应用服务**: http://127.0.0.1:8000
- **后台管理**: http://127.0.0.1:8000/admin
- **API 文档**: http://127.0.0.1:8000/docs
- **Mintlify 文档**: http://127.0.0.1:3000
- **健康检查**: http://127.0.0.1:8000/health

### 生产环境 Docker 部署

#### 构建和推送镜像

```bash
# 构建镜像
docker build -t arbitrage-tool:latest .

# 标签镜像（以便推送到仓库）
docker tag arbitrage-tool:latest your-registry/arbitrage-tool:latest

# 推送到镜像仓库（Docker Hub、AWS ECR、Azure ACR 等）
docker push your-registry/arbitrage-tool:latest

# 在服务器上拉取并运行
docker pull your-registry/arbitrage-tool:latest
docker run -d \
  --name arbitrage-tool \
  -p 8000:8000 \
  --env-file .env \
  -v arbitrage-data:/app/data \
  your-registry/arbitrage-tool:latest
```

#### 使用 Docker Compose 部署整个技术栈

```bash
# 在生产服务器上启动完整的应用栈
docker compose -f docker-compose.yml up -d --build

# 验证所有服务
docker compose ps

# 查看应用日志
docker compose logs -f app

# 升级服务（拉取最新镜像并重启）
docker compose pull
docker compose up -d
```

### 容器管理命令

```bash
# 查看所有容器
docker compose ps

# 查看特定服务日志
docker compose logs app
docker compose logs postgres
docker compose logs redis

# 进入容器进行调试
docker compose exec app /bin/bash
docker compose exec postgres psql -U arbitrage -d arbitrage

# 重启单个服务
docker compose restart app

# 停止所有服务
docker compose down

# 停止并删除数据卷
docker compose down -v

# 清理未使用的镜像和卷
docker system prune -a
```

## GitHub Actions CI/CD 流程

本项目配置了企业级的 GitHub Actions 自动化流程，提供代码质量控制、自动化测试、安全扫描和文档部署。

### CI 工作流（.github/workflows/ci.yml）

**触发条件**：任何 push 或 PR 到 `main`/`develop` 分支

**自动执行的检查**：

```
┌─ 代码质量检查
│  ├─ Flake8：语法和风格检查
│  ├─ Black：代码格式化验证
│  └─ isort：Import 排序检查
│
├─ 单元测试
│  ├─ Python 3.10 环境
│  ├─ Python 3.11 环境
│  ├─ Python 3.12 环境
│  └─ 代码覆盖率上报（Codecov）
│
├─ Docker 镜像构建
│  └─ 构建应用镜像（仅在 main 分支）
│
├─ 安全扫描
│  ├─ Bandit：Python 代码安全扫描
│  ├─ Safety：依赖包漏洞检查
│  └─ TruffleHog：敏感信息泄露检测
│
└─ 文档构建
   └─ Mintlify 文档链接验证
```

**运行时间**：~10-12 分钟

**监控方式**：
1. GitHub Actions 标签 → "CI/CD Pipeline"
2. 点击最新的工作流运行
3. 查看各步骤的执行日志

### 文档部署工作流（.github/workflows/deploy-docs.yml）

**触发条件**：Push 到 main 分支 + mintlify-docs/ 文件变更

**自动执行**：

```
构建 Mintlify 文档
  ├─ Node.js 18 环境
  ├─ npm 依赖安装（启用缓存）
  ├─ 链接完整性检查（npm run broken-links）
  └─ Mintlify 输出准备

部署到 GitHub Pages
  └─ Static HTML 部署（无需 Jekyll 重复编译）
```

**运行时间**：~3-5 分钟

**文档访问地址**：https://hungyann.github.io/arbitrage_tool/

### 本地开发和 CI 同步

#### 安装开发工具

```bash
# 安装代码检查和测试工具
pip install black isort flake8 bandit pytest pytest-cov

# 或使用 pre-commit hooks（推荐自动检查）
pip install pre-commit
pre-commit install
```

#### 提交前本地检查

```bash
# 自动格式化代码
black app tests
isort app tests

# 检查代码风格
flake8 app tests

# 运行单元测试
pytest tests/ -v --cov=app --cov-report=html

# 安全扫描
bandit -r app
```

#### 完整的本地模拟 CI 环境

```bash
# 启动 Docker 开发环境
docker compose up -d

# 运行所有检查
black --check app tests
isort --check-only app tests
flake8 app tests
pytest tests/ -v --cov=app
bandit -r app

# 检查 Mintlify 文档
cd mintlify-docs
npm install
npm run broken-links
cd ..
```

### 分支保护和代码审查流程

**推荐的分支保护规则**（Settings → Branches）：

1. Branch name pattern：`main`
2. 启用以下选项：
   - ✅ Require a pull request before merging
   - ✅ Require approvals（至少 1 个）
   - ✅ Require status checks to pass
   - ✅ Require branches to be up to date before merging
   - ✅ Dismiss stale pull request approvals when new commits are pushed

这样强制所有 PR 必须通过 CI 检查且获得代码审查才能合并。

**标准工作流**：

1. 创建 feature 分支：`git checkout -b feature/your-feature`
2. 进行开发并提交：`git commit -m "feat: add feature"`
3. Push 到 GitHub：`git push origin feature/your-feature`
4. 创建 Pull Request
5. GitHub Actions 自动运行 CI 检查
6. 等待检查通过（绿色 ✅）
7. 请求代码审查和 Approve
8. 合并到 main 分支
9. 自动部署文档和应用

### CI/CD 故障排查

**PR 检查失败怎么办？**

1. 查看 Actions 标签中的失败日志
2. 本地运行相同的检查命令
3. 修复问题后重新 push
4. CI 自动重新运行检查

**常见问题**：

| 问题 | 原因 | 解决方案 |
|------|------|--------|
| Flake8 失败 | 代码风格不符合规范 | 运行 `black app tests` 后重新提交 |
| Black 失败 | 代码格式错误 | 运行 `black app tests` 格式化代码 |
| isort 失败 | Import 排序错误 | 运行 `isort app tests` 排序 import |
| 测试失败 | 单元测试不通过 | 本地运行 `pytest` 调试并修复 |
| Bandit 失败 | 代码有安全问题 | 查看日志中的安全建议并修复 |
| 文档部署失败 | 链接检查失败 | 检查 `npm run broken-links` 输出并修复链接 |

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

## 生产级安全机制

**交易模式控制**
- 默认 `TRADING_MODE=paper`，仅做模拟交易，不涉及真实资金
- 切换到 `TRADING_MODE=live` 启用实盘交易，需要显式配置和确认
- 额外的 `BINANCE_LIVE_TRADING=true` 开关确保实盘意图明确

**风险控制**
- 每次下单前检查：余额、手续费、滑点、最小下单额、最大单笔金额
- 单日亏损上限：防止超出风险承受范围
- 网格策略限制：最多开仓份数和资金分配比例
- 价格硬边界：买入和卖出的绝对价格上下限

**凭证管理**
- API key 和密钥绝不写进代码，仅存储在环境变量或 VPS secret 中
- 支持多种认证方式：密码、API key、MFA（后续支持）
- 后台管理界面需登录认证，会话有过期时间

**可观测性和审计**
- 完整的日志系统：所有交易、决策、错误都被记录
- 事件追踪：行情变化、策略触发、订单执行、异常处理
- 日志查询接口：便于事后审计和性能优化
- 实时告警：通过 Telegram 推送关键事件

**部署安全**
- Docker 容器隔离：应用、数据库、缓存相互隔离
- HTTPS 支持：生产环境应使用 TLS 加密通信
- 数据持久化：订单、日志、配置保存在数据库，不依赖内存
- 自动备份：定期备份交易数据和配置

## 📚 文档和资源

### 项目文档

| 文档 | 说明 | 位置 |
|------|------|------|
| **README** | 项目概述、快速开始 | [README.md](README.md) |
| **MIT License** | 开源许可证 | [LICENSE](LICENSE) | 
| **环境变量示例** | 配置模板 | [.env.example](.env.example) |
| **产品规格书** | 需求文档 | [docs/product_tool_document.md](docs/product_tool_document.md) |

### CI/CD 和部署指南

| 文档 | 说明 | 位置 |
|------|------|------|
| **CI/CD 完整指南** | GitHub Actions 工作流、本地开发工具 | [.github/CI-CD-GUIDE.md](.github/CI-CD-GUIDE.md) |
| **Mintlify 部署指南** | 文档构建、GitHub Pages 配置、常见问题 | [.github/MINTLIFY-DEPLOYMENT.md](.github/MINTLIFY-DEPLOYMENT.md) |
| **GitHub Actions 工作流** | 代码质量、测试、安全扫描 | [.github/workflows/ci.yml](.github/workflows/ci.yml) |
| **文档部署工作流** | Mintlify 构建和部署配置 | [.github/workflows/deploy-docs.yml](.github/workflows/deploy-docs.yml) |

### 在线文档

| 文档 | 链接 |
|------|------|
| **项目文档网站** | [https://hungyann.github.io/arbitrage_tool/](https://hungyann.github.io/arbitrage_tool/) |
| **GitHub 仓库** | [https://github.com/HungYann/arbitrage_tool](https://github.com/HungYann/arbitrage_tool) |
| **GitHub Releases** | [https://github.com/HungYann/arbitrage_tool/releases](https://github.com/HungYann/arbitrage_tool/releases) |

### 开发和部署

| 工具/框架 | 用途 | 配置文件 |
|---------|------|--------|
| **FastAPI** | 后端 API 框架 | [app/main.py](app/main.py) |
| **Mintlify** | 文档框架 | [mintlify-docs/docs.json](mintlify-docs/docs.json) |
| **Docker Compose** | 容器编排 | [docker-compose.yml](docker-compose.yml) |
| **Dockerfile** | 应用容器配置 | [Dockerfile](Dockerfile) |
| **Python 配置** | 代码风格和测试 | [pyproject.toml](pyproject.toml) |
| **Flake8 配置** | Python 代码检查 | [.flake8](.flake8) |

## 🔗 快速链接

<div align="center">

| 📖 文档 | 🚀 部署 | 💻 开发 | 📞 支持 |
|--------|--------|--------|--------|
| [完整文档](https://hungyann.github.io/arbitrage_tool/) | [Docker Compose](docker-compose.yml) | [GitHub Repo](https://github.com/HungYann/arbitrage_tool) | [GitHub Issues](https://github.com/HungYann/arbitrage_tool/issues) |
| [快速开始](#快速启动) | [AWS EC2](README.md#-aws-ec2部署) | [CI/CD 指南](.github/CI-CD-GUIDE.md) | [讨论区](https://github.com/HungYann/arbitrage_tool/discussions) |
| [API 文档](https://hungyann.github.io/arbitrage_tool/reference/api-overview.html) | [Mintlify 部署](.github/MINTLIFY-DEPLOYMENT.md) | [本地开发](README.md#-本地开发) | [提交 PR](https://github.com/HungYann/arbitrage_tool/pulls) |

</div>

---

## 📊 项目统计

<div align="center">

![GitHub Repo stars](https://img.shields.io/github/stars/HungYann/arbitrage_tool?style=social)
![GitHub watchers](https://img.shields.io/github/watchers/HungYann/arbitrage_tool?style=social)
![GitHub forks](https://img.shields.io/github/forks/HungYann/arbitrage_tool?style=social)

![Last commit](https://img.shields.io/github/last-commit/HungYann/arbitrage_tool)
![Repo size](https://img.shields.io/github/repo-size/HungYann/arbitrage_tool)
![Language](https://img.shields.io/github/languages/top/HungYann/arbitrage_tool)

</div>

---

## 💡 技术栈

<div align="center">

| 后端 | 前端 | 中间件 | 部署 | 测试 |
|------|------|--------|------|------|
| ![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-green?logo=fastapi) | ![HTML/CSS/JS](https://img.shields.io/badge/HTML%2FCSS%2FJS-modern-blue) | ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue?logo=postgresql) | ![Docker](https://img.shields.io/badge/Docker-blue?logo=docker) | ![Pytest](https://img.shields.io/badge/Pytest-7+-blue) |
| ![Python 3.11](https://img.shields.io/badge/Python-3.11+-blue?logo=python) | ![Mintlify](https://img.shields.io/badge/Mintlify-docs-purple) | ![Redis](https://img.shields.io/badge/Redis-7-red?logo=redis) | ![GitHub Pages](https://img.shields.io/badge/GitHub%20Pages-deployment-blue) | ![Coverage](https://img.shields.io/badge/Coverage-pytest--cov-blue) |
| ![Uvicorn](https://img.shields.io/badge/Uvicorn-ASGI-green) | ![OpenAPI](https://img.shields.io/badge/OpenAPI-documentation-green) | ![CCXT](https://img.shields.io/badge/CCXT-exchange%20API-orange) | ![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-CI%2FCD-blue) | ![Code Quality](https://img.shields.io/badge/Black-code%20formatter-black) |

</div>

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

**MIT License © 2026 Andrew Liu**
