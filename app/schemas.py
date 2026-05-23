from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class StrategyConfigPayload(BaseModel):
    total_capital_usd: float = Field(30_000.0, ge=500, le=200_000)
    tranche_count: int = Field(10, ge=1, le=20)
    strategy_mode: Literal["static", "gradient"] = "gradient"
    reference_price: float = Field(1.0, gt=0)
    buy_threshold_bps: float = Field(5.0, ge=0)
    min_profit_bps: float = Field(5.0, ge=0)
    fee_bps: float = Field(0.0, ge=0)
    slippage_bps: float = Field(0.0, ge=0)
    min_notional_usd: float = Field(10.0, gt=0)
    max_open_tranches: int = Field(10, ge=1, le=20)
    max_buy_price: float = Field(0.9994, gt=0)
    min_sell_price: float = Field(1.0, gt=0)
    grid_step: float = Field(0.0005, gt=0)
    min_buy_price: float = Field(0.9900, gt=0)
    max_usdt_allocation_pct: float = Field(1.0, gt=0, le=1.0)
    max_live_order_notional_usd: float = Field(0.0, ge=0)

    @model_validator(mode="after")
    def validate_position_limits(self) -> "StrategyConfigPayload":
        if self.max_open_tranches > self.tranche_count:
            raise ValueError("max_open_tranches cannot exceed tranche_count")
        return self


class TickRequest(BaseModel):
    price: float = Field(..., gt=0, description="Current USDT/USD price")
    execute: bool = Field(False, description="Apply the decision to the paper portfolio")


class BrokerTradeRequest(BaseModel):
    price: float | None = Field(None, gt=0, description="Optional override price. If omitted, service fetches Binance quote.")


class DecisionResponse(BaseModel):
    action: str
    reason: str
    price: float
    notional_usd: float
    tranche_id: str | None
    grid_index: int | None
    expected_profit_usd: float
    expected_profit_bps: float
    expected_gross_profit_bps: float
    executed: bool


class TrancheResponse(BaseModel):
    id: str
    entry_price: float
    notional_usd: float
    usdt_amount: float
    opened_at: str
    grid_index: int | None


class StateResponse(BaseModel):
    usd_available: float
    usdt_available: float
    realized_profit_usd: float
    open_tranches: list[TrancheResponse]
