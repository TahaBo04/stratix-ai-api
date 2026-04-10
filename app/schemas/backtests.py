"""Backtest schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BacktestCreateRequest(BaseModel):
    initial_capital: float = Field(default=10_000.0, gt=0)
    fees_bps: float = Field(default=10.0, ge=0, le=500)
    slippage_bps: float = Field(default=5.0, ge=0, le=500)


class MetricCard(BaseModel):
    key: str
    label: str
    value: float
    display_value: str


class ChartPoint(BaseModel):
    timestamp: str
    value: float


class PricePoint(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float


class TradeMarker(BaseModel):
    timestamp: str
    side: str
    price: float
    marker_type: str


class TradeRecord(BaseModel):
    id: str
    side: str
    entry_time: str
    entry_price: float
    exit_time: str
    exit_price: float
    qty: float
    pnl: float
    pnl_pct: float
    exit_reason: str


class BacktestRunResponse(BaseModel):
    id: str
    strategy_version_id: str
    status: str
    error_message: str | None = None
    asset_symbol: str
    asset_class: str
    market: str
    timeframe: str
    date_start: str
    date_end: str
    initial_capital: float
    fees_bps: float
    slippage_bps: float
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class BacktestResultResponse(BaseModel):
    run: BacktestRunResponse
    metrics: list[MetricCard]
    summary: dict[str, Any]
    generated_python: str
    price_series: list[PricePoint]
    equity_curve: list[ChartPoint]
    drawdown_curve: list[ChartPoint]
    trade_markers: list[TradeMarker]
    trades: list[TradeRecord]


class HistoryItem(BaseModel):
    strategy_id: str
    strategy_name: str
    run_id: str
    status: str
    created_at: datetime
    timeframe: str
    asset_symbol: str
    summary: dict[str, Any]
