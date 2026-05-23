# AI 产品工具文档：开源套利工具列表与实现方案

## 1. 产品定位

这是一个开源套利工具的产品文档和 FastAPI 原型。它不是“保证赚钱”的交易机器人，而是一个可审计、可配置、可在 VPS 上长期运行的自动化交易基础设施。

核心场景：

- 默认资金规模为 30,000 USD。
- 交易标的以 `USDT/USD`、稳定币/法币或稳定币/稳定币价差为主。
- 策略要求把资金拆成多份，允许多次买入、多次卖出。
- 每份只要覆盖手续费和滑点后达到可调收益阈值，例如万分之五，就可以成交。
- 所有行情、决策、模拟成交、实盘成交、错误都需要落日志。

## 2. 开源工具列表

| 工具 | 用途 | 适合场景 | 局限 |
| --- | --- | --- | --- |
| [CCXT](https://github.com/ccxt/ccxt) | 统一交易所 REST API | 自己写策略、下单、查余额、查 ticker | 主要是适配层，不提供完整策略系统 |
| [Hummingbot](https://hummingbot.org/) | 开源做市/套利机器人 | 跨交易所套利、做市策略、连接器生态 | 架构较重，二次开发成本更高 |
| [Freqtrade](https://www.freqtrade.io/en/stable/) | 开源加密货币交易机器人 | 策略回测、自动交易、风控 | 更偏趋势/量化策略，不是专门的稳定币价差库存系统 |
| [NautilusTrader](https://nautilustrader.io/) | 专业级算法交易平台 | 事件驱动、多资产、回测和实盘统一 | 学习曲线较高 |
| [Jesse](https://docs.jesse.trade/) | Python 策略框架 | 策略开发和回测 | 对本产品这种轻量 VPS 工具可能偏重 |
| [FastAPI](https://fastapi.tiangolo.com/) | API 服务层 | 暴露状态、配置、日志、手动触发、健康检查 | 不负责交易逻辑，需要自己实现策略和 broker |

建议路径：

第一阶段用 FastAPI + 纯 Python 策略引擎 + 纸面 Broker，把逻辑跑通。第二阶段接 CCXT 做交易所适配。第三阶段再评估是否迁移或接入 Hummingbot 这类成熟交易框架。

## 3. 策略设计

### 固定阈值方案

用户举例的规则很清晰：

- 当前 `USDT/USD = 0.9994` 或更低，用 USD 买入 USDT。
- 当前 `USDT/USD = 1.0000` 或更高，卖出 USDT 换成 USD。
- 差价是 `0.0005`，也就是约万分之五。

这个方案容易理解，但缺点是只用一个阈值，不能很好处理连续下跌、连续反弹、不同批次成本不同的问题。

### 多份网格库存方案

更灵活的方案是把资金拆为多个 tranche，并按 PRD v1.1 增加硬边界：

- `total_capital = 30000`
- `tranche_count = 1~10`，默认 `10`
- 默认单份资金约 `10000 USD`
- `strategy_mode = gradient`
- `max_buy_price = 0.9994`
- `min_sell_price = 1.0000`
- `grid_step = 0.0005`
- `min_buy_price = 0.9900`
- `min_profit_bps = 5`

当价格高于 `0.9994` 时绝不买入；当价格低于 `1.0000` 时绝不卖出；`0.9995 ~ 0.9999` 是静默区间。动态梯度模式下，买入档位从 `0.9994` 向下按 `0.0005` 排列，同一档位只开一份：

```text
#1 <= 0.9994
#2 <= 0.9990
#3 <= 0.9985
```

每份记录：

- 买入价格
- 买入金额
- 获得 USDT 数量
- 梯度档位 `grid_index`
- 手续费和滑点估算
- 目标卖出价
- 当前未实现利润

卖出时先检查 `min_sell_price` 硬下限，再遍历每份库存。只有某份库存当前卖出后可以覆盖费用并达到最小收益阈值，才卖出这一份。

## 4. 利润计算

设：

- `entry_price` 为买入价格
- `exit_price` 为当前卖出价格
- `notional_usd` 为买入金额
- `fee_bps` 为单边手续费，单位 bps
- `slippage_bps` 为单边滑点，单位 bps
- `min_profit_bps` 为最低目标收益，单位 bps

买入获得：

```text
usdt_amount = notional_usd / entry_price * (1 - fee_bps / 10000 - slippage_bps / 10000)
```

卖出获得：

```text
gross_usd = usdt_amount * exit_price
net_usd = gross_usd * (1 - fee_bps / 10000 - slippage_bps / 10000)
profit = net_usd - notional_usd
profit_bps = profit / notional_usd * 10000
```

只有 `profit_bps >= min_profit_bps` 时，才允许卖出。

## 5. FastAPI 工具功能

当前原型提供：

- `GET /health`：健康检查。
- `GET /config`：查看策略配置。
- `PUT /config`：更新策略配置。
- `GET /state`：查看账户、库存、累计盈亏。
- `POST /tick`：传入价格，返回策略决策；可选 `execute=true` 执行纸面成交。
- `GET /logs`：查看最近日志。
- `POST /reset`：重置纸面账户。

默认只支持纸面交易。后续实盘版本建议新增：

- `Broker` 接口：`fetch_balance`、`fetch_ticker`、`create_order`。
- `CcxtBroker`：读取环境变量中的 API key。
- 风控模块：单笔上限、日亏损上限、API 失败熔断、余额异常熔断。
- 日志持久化：JSONL + SQLite 或 Postgres。

## 6. VPS 部署建议

建议目录：

```text
/opt/open-arbitrage-tool
  app/
  data/
    events.jsonl
  .env
  requirements.txt
```

用 systemd 托管：

```ini
[Unit]
Description=Open Arbitrage Tool
After=network.target

[Service]
WorkingDirectory=/opt/open-arbitrage-tool
EnvironmentFile=/opt/open-arbitrage-tool/.env
ExecStart=/opt/open-arbitrage-tool/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## 7. 风控清单

- API key 只给交易权限，不给提现权限。
- 实盘前至少纸面运行 1-2 周。
- 所有下单必须记录 request、response、client order id。
- 交易所返回异常时不重试无限下单。
- 价格来源要校验时间戳，过期行情不交易。
- 资金拆份不能全部一次打满，保留 USD 和 USDT 两侧库存。
- 参数变更要记录日志。
