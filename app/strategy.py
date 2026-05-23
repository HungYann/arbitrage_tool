from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable
from uuid import uuid4


class Action(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass(slots=True)
class StrategyConfig:
    total_capital_usd: float = 30_000.0
    tranche_count: int = 10
    strategy_mode: str = "gradient"
    reference_price: float = 1.0
    buy_threshold_bps: float = 5.0
    min_profit_bps: float = 5.0
    fee_bps: float = 0.0
    slippage_bps: float = 0.0
    min_notional_usd: float = 10.0
    max_open_tranches: int = 10
    max_buy_price: float = 0.9994
    min_sell_price: float = 1.0
    grid_step: float = 0.0005
    min_buy_price: float = 0.9900
    max_usdt_allocation_pct: float = 1.0
    max_live_order_notional_usd: float = 0.0

    def __post_init__(self) -> None:
        if not 500 <= self.total_capital_usd <= 200_000:
            raise ValueError("total_capital_usd must be between 500 and 200000")
        if not 1 <= self.tranche_count <= 20:
            raise ValueError("tranche_count must be between 1 and 20")
        if not 1 <= self.max_open_tranches <= 20:
            raise ValueError("max_open_tranches must be between 1 and 20")
        if self.max_open_tranches > self.tranche_count:
            raise ValueError("max_open_tranches cannot exceed tranche_count")

    @property
    def tranche_size_usd(self) -> float:
        return self.total_capital_usd / self.tranche_count

    @property
    def round_trip_cost_bps(self) -> float:
        return 2 * (self.fee_bps + self.slippage_bps)

    @property
    def buy_trigger_price(self) -> float:
        return min(self.max_buy_price, self.reference_price * (1 - self.buy_threshold_bps / 10_000))


@dataclass(slots=True)
class Tranche:
    id: str
    entry_price: float
    notional_usd: float
    usdt_amount: float
    opened_at: str
    grid_index: int | None = None


@dataclass(slots=True)
class Portfolio:
    usd_available: float
    usdt_available: float = 0.0
    realized_profit_usd: float = 0.0
    open_tranches: list[Tranche] = field(default_factory=list)

    @classmethod
    def from_config(cls, config: StrategyConfig) -> "Portfolio":
        return cls(usd_available=0.0, usdt_available=config.total_capital_usd)


@dataclass(slots=True)
class Decision:
    action: Action
    reason: str
    price: float
    notional_usd: float = 0.0
    tranche_id: str | None = None
    grid_index: int | None = None
    expected_profit_usd: float = 0.0
    expected_profit_bps: float = 0.0
    expected_gross_profit_bps: float = 0.0


class GridArbitrageEngine:
    def __init__(self, config: StrategyConfig):
        self.config = config

    def evaluate(self, price: float, portfolio: Portfolio) -> Decision:
        if price <= 0:
            return Decision(Action.HOLD, "price must be positive", price)

        if price <= self.config.buy_trigger_price:
            buy_candidate = self._best_buyback_candidate(price, portfolio.open_tranches)
        else:
            buy_candidate = None

        if buy_candidate is not None:
            tranche, profit_usd, profit_bps, gross_profit_bps = buy_candidate
            return Decision(
                action=Action.BUY,
                reason="price reached buy cap and open sell tranche reached minimum profit",
                price=price,
                notional_usd=tranche.notional_usd,
                tranche_id=tranche.id,
                grid_index=tranche.grid_index,
                expected_profit_usd=profit_usd,
                expected_profit_bps=profit_bps,
                expected_gross_profit_bps=gross_profit_bps,
            )

        if price >= self.config.min_sell_price:
            if not self._can_open_tranche(portfolio, price):
                return Decision(Action.HOLD, "no capacity or USDT balance for a new sell tranche", price)
            grid_index = len(portfolio.open_tranches) + 1
            notional = min(self.config.tranche_size_usd, portfolio.usdt_available * price)
            if notional >= self.config.min_notional_usd:
                return Decision(
                    action=Action.SELL,
                    reason="price is at or above sell floor",
                    price=price,
                    notional_usd=notional,
                    grid_index=grid_index,
                )

        if price < self.config.min_sell_price:
            return Decision(Action.HOLD, "price is inside quiet band", price)
        return Decision(Action.HOLD, "price reached sell floor but no capacity to open a sell tranche", price)

    def apply(self, decision: Decision, portfolio: Portfolio) -> Portfolio:
        if decision.action == Action.SELL and not decision.tranche_id:
            self._apply_sell_open(decision, portfolio)
        elif decision.action == Action.BUY and decision.tranche_id:
            self._apply_buyback(decision, portfolio)
        return portfolio

    def estimate_buyback(self, tranche: Tranche, buy_price: float) -> tuple[float, float]:
        cost_rate = (self.config.fee_bps + self.config.slippage_bps) / 10_000
        bought_usdt = tranche.notional_usd / buy_price * (1 - cost_rate)
        profit_usdt = bought_usdt - tranche.usdt_amount
        profit_usd = profit_usdt * buy_price
        profit_bps = profit_usdt / tranche.usdt_amount * 10_000
        return profit_usd, profit_bps

    def estimate_gross_profit_bps(self, tranche: Tranche, buy_price: float) -> float:
        bought_usdt = tranche.notional_usd / buy_price
        return (bought_usdt - tranche.usdt_amount) / tranche.usdt_amount * 10_000

    def _apply_sell_open(self, decision: Decision, portfolio: Portfolio) -> None:
        cost_rate = (self.config.fee_bps + self.config.slippage_bps) / 10_000
        usdt_amount = decision.notional_usd / decision.price
        usd_proceeds = usdt_amount * decision.price * (1 - cost_rate)
        portfolio.usdt_available -= usdt_amount
        portfolio.usd_available += usd_proceeds
        portfolio.open_tranches.append(
            Tranche(
                id=str(uuid4()),
                entry_price=decision.price,
                notional_usd=usd_proceeds,
                usdt_amount=usdt_amount,
                opened_at=datetime.now(timezone.utc).isoformat(),
                grid_index=decision.grid_index,
            )
        )

    def _apply_buyback(self, decision: Decision, portfolio: Portfolio) -> None:
        index = next(
            (i for i, tranche in enumerate(portfolio.open_tranches) if tranche.id == decision.tranche_id),
            None,
        )
        if index is None:
            return

        tranche = portfolio.open_tranches.pop(index)
        cost_rate = (self.config.fee_bps + self.config.slippage_bps) / 10_000
        bought_usdt = tranche.notional_usd / decision.price * (1 - cost_rate)
        profit_usdt = bought_usdt - tranche.usdt_amount
        portfolio.usd_available -= tranche.notional_usd
        portfolio.usdt_available += bought_usdt
        portfolio.realized_profit_usd += profit_usdt * decision.price

    def _best_buyback_candidate(
        self, price: float, tranches: Iterable[Tranche]
    ) -> tuple[Tranche, float, float, float] | None:
        candidates: list[tuple[Tranche, float, float, float]] = []
        required_bps = self.config.min_profit_bps
        for tranche in tranches:
            profit_usd, profit_bps = self.estimate_buyback(tranche, price)
            gross_profit_bps = self.estimate_gross_profit_bps(tranche, price)
            if profit_bps >= required_bps:
                candidates.append((tranche, profit_usd, profit_bps, gross_profit_bps))

        if not candidates:
            return None
        return max(candidates, key=lambda item: item[2])

    def _can_open_tranche(self, portfolio: Portfolio, price: float) -> bool:
        usd_value = portfolio.usd_available
        max_usd_value = self.config.total_capital_usd * self.config.max_usdt_allocation_pct
        return (
            portfolio.usdt_available * price >= self.config.min_notional_usd
            and len(portfolio.open_tranches) < self.config.max_open_tranches
            and usd_value < max_usd_value
        )
