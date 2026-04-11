"""Serialization helpers for backtest responses."""
from __future__ import annotations

from app.schemas.backtests import ChartPoint, MetricCard, PricePoint, TradeMarker, TradeRecord


def build_metric_cards(summary: dict) -> list[MetricCard]:
    return [
        MetricCard(key="win_rate", label="Win Rate", value=summary.get("win_rate", 0.0), display_value=f"{summary.get('win_rate', 0.0):.2f}%"),
        MetricCard(key="total_pnl", label="Total PnL", value=summary.get("total_pnl", 0.0), display_value=f"${summary.get('total_pnl', 0.0):,.2f}"),
        MetricCard(key="net_return_pct", label="Net Return", value=summary.get("net_return_pct", 0.0), display_value=f"{summary.get('net_return_pct', 0.0):.2f}%"),
        MetricCard(key="max_drawdown_pct", label="Max Drawdown", value=summary.get("max_drawdown_pct", 0.0), display_value=f"{summary.get('max_drawdown_pct', 0.0):.2f}%"),
        MetricCard(key="profit_factor", label="Profit Factor", value=summary.get("profit_factor", 0.0), display_value=f"{summary.get('profit_factor', 0.0):.2f}"),
        MetricCard(key="sharpe_ratio", label="Sharpe", value=summary.get("sharpe_ratio", 0.0), display_value=f"{summary.get('sharpe_ratio', 0.0):.2f}"),
        MetricCard(key="trade_count", label="Trades", value=float(summary.get("trade_count", 0)), display_value=str(summary.get("trade_count", 0))),
    ]


def serialize_price_series(rows: list[dict]) -> list[PricePoint]:
    return [PricePoint(timestamp=row["timestamp"], open=row["open"], high=row["high"], low=row["low"], close=row["close"]) for row in rows]


def serialize_equity_curve(rows: list[dict]) -> list[ChartPoint]:
    return [ChartPoint(timestamp=row["timestamp"], value=row["equity"]) for row in rows]


def serialize_drawdown_curve(rows: list[dict]) -> list[ChartPoint]:
    return [ChartPoint(timestamp=row["timestamp"], value=row["drawdown_pct"]) for row in rows]


def serialize_trade_markers(trades: list[dict]) -> list[TradeMarker]:
    markers: list[TradeMarker] = []
    for trade in trades:
        markers.append(TradeMarker(timestamp=trade["entry_time"], side=trade["side"], price=trade["entry_price"], marker_type="entry"))
        markers.append(TradeMarker(timestamp=trade["exit_time"], side=trade["side"], price=trade["exit_price"], marker_type="exit"))
    return markers


def serialize_trades(trades: list[dict]) -> list[TradeRecord]:
    return [TradeRecord(**trade) for trade in trades]
