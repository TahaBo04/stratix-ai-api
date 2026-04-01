"""Deterministic backtesting engine for structured strategies."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pandas as pd

from app.models import CompiledRule, CompiledStrategy
from app.services.indicators import compute_indicator
from app.services.metrics import summarize_trades


@dataclass(slots=True)
class Position:
    side: str
    entry_time: str
    entry_price: float
    qty: float
    invested_capital: float
    stop_price: float | None
    take_profit_price: float | None


def run_backtest(strategy: CompiledStrategy, frame: pd.DataFrame, initial_capital: float) -> dict:
    working = frame.copy()
    indicator_series = {}
    for indicator in strategy.indicators:
        payload = {"type": indicator.indicator_type, **indicator.params}
        indicator_series[indicator.identifier] = compute_indicator(working, payload)
        working[indicator.identifier] = indicator_series[indicator.identifier]

    entry_signal = _evaluate_rule(strategy.entry_rule, working)
    exit_signal = _evaluate_rule(strategy.exit_rule, working) if strategy.exit_rule else pd.Series(False, index=working.index)

    cash = initial_capital
    position: Position | None = None
    trades: list[dict] = []
    equity_points: list[dict] = []
    fees_bps = float(strategy.costs.get("fees_bps", 0.0))
    slippage_bps = float(strategy.costs.get("slippage_bps", 0.0))

    for idx in range(1, len(working)):
        row = working.iloc[idx]
        timestamp = row["timestamp"].isoformat()

        if position is not None:
            exit_fill = _check_position_exit(position, strategy.direction, row, exit_signal.iloc[idx - 1], strategy)
            if exit_fill is not None:
                raw_exit_price, reason = exit_fill
                exit_price = _apply_exit_costs(position.side, raw_exit_price, slippage_bps)
                gross_exit = position.qty * exit_price
                exit_fee = gross_exit * fees_bps / 10_000
                net_exit = gross_exit - exit_fee
                pnl = net_exit - position.invested_capital
                cash = net_exit
                trades.append(
                    {
                        "id": str(uuid4()),
                        "side": position.side,
                        "entry_time": position.entry_time,
                        "entry_price": round(position.entry_price, 4),
                        "exit_time": timestamp,
                        "exit_price": round(exit_price, 4),
                        "qty": round(position.qty, 8),
                        "pnl": round(pnl, 2),
                        "pnl_pct": round((pnl / position.invested_capital) * 100 if position.invested_capital else 0.0, 2),
                        "exit_reason": reason,
                    }
                )
                position = None

        if position is None and bool(entry_signal.iloc[idx - 1]):
            entry_price = _apply_entry_costs(strategy.direction, float(row["open"]), slippage_bps)
            entry_fee = cash * fees_bps / 10_000
            invested = max(cash - entry_fee, 0.0)
            if invested > 0:
                qty = invested / entry_price
                stop_price, take_profit_price = _compute_risk_prices(strategy.direction, entry_price, strategy.risk)
                position = Position(
                    side=strategy.direction,
                    entry_time=timestamp,
                    entry_price=entry_price,
                    qty=qty,
                    invested_capital=invested,
                    stop_price=stop_price,
                    take_profit_price=take_profit_price,
                )
                cash = 0.0

        marked_equity = cash
        if position is not None:
            mark_price = float(row["close"])
            if position.side == "long":
                marked_equity = position.qty * mark_price
            else:
                marked_equity = position.invested_capital + (position.entry_price - mark_price) * position.qty
        equity_points.append({"timestamp": timestamp, "equity": round(marked_equity, 2), "drawdown_pct": 0.0})

    if position is not None:
        last_row = working.iloc[-1]
        exit_price = _apply_exit_costs(position.side, float(last_row["close"]), slippage_bps)
        reason = "end_of_data"
        gross_exit = position.qty * exit_price
        exit_fee = gross_exit * fees_bps / 10_000
        net_exit = gross_exit - exit_fee
        pnl = net_exit - position.invested_capital
        cash = net_exit
        trades.append(
            {
                "id": str(uuid4()),
                "side": position.side,
                "entry_time": position.entry_time,
                "entry_price": round(position.entry_price, 4),
                "exit_time": last_row["timestamp"].isoformat(),
                "exit_price": round(exit_price, 4),
                "qty": round(position.qty, 8),
                "pnl": round(pnl, 2),
                "pnl_pct": round((pnl / position.invested_capital) * 100 if position.invested_capital else 0.0, 2),
                "exit_reason": reason,
            }
        )
        if equity_points:
            equity_points[-1]["equity"] = round(cash, 2)

    peak = 0.0
    for point in equity_points:
        peak = max(peak, point["equity"])
        point["drawdown_pct"] = round(((peak - point["equity"]) / peak) * 100 if peak else 0.0, 2)

    summary = summarize_trades(trades, equity_points, initial_capital, cash if equity_points else initial_capital)

    price_rows = [
        {
            "timestamp": row["timestamp"].isoformat(),
            "open": round(float(row["open"]), 4),
            "high": round(float(row["high"]), 4),
            "low": round(float(row["low"]), 4),
            "close": round(float(row["close"]), 4),
        }
        for _, row in working.iterrows()
    ]
    return {
        "summary": summary,
        "trades": trades,
        "equity_curve": equity_points,
        "price_series": price_rows,
    }


def _compute_risk_prices(direction: str, entry_price: float, risk: dict) -> tuple[float | None, float | None]:
    stop_type = risk.get("stop_loss_type", "percent")
    stop_value = float(risk.get("stop_loss_value", 0.0))
    rr = float(risk.get("risk_reward_ratio", 2.0))
    take_profit_type = risk.get("take_profit_type", "derived_from_rr")
    take_profit_value = risk.get("take_profit_value")

    stop_price = None
    take_profit_price = None
    if stop_type == "percent":
        if direction == "long":
            stop_price = entry_price * (1 - stop_value / 100)
        else:
            stop_price = entry_price * (1 + stop_value / 100)
    if take_profit_type == "fixed_percent" and take_profit_value:
        if direction == "long":
            take_profit_price = entry_price * (1 + float(take_profit_value) / 100)
        else:
            take_profit_price = entry_price * (1 - float(take_profit_value) / 100)
    elif take_profit_type == "derived_from_rr" and stop_value:
        if direction == "long":
            take_profit_price = entry_price * (1 + (stop_value * rr) / 100)
        else:
            take_profit_price = entry_price * (1 - (stop_value * rr) / 100)
    return stop_price, take_profit_price


def _check_position_exit(position: Position, direction: str, row: pd.Series, exit_signal: bool, strategy: CompiledStrategy) -> tuple[float, str] | None:
    high = float(row["high"])
    low = float(row["low"])
    open_price = float(row["open"])

    if direction == "long":
        if position.stop_price is not None and position.take_profit_price is not None:
            if low <= position.stop_price and high >= position.take_profit_price:
                return position.stop_price, "stop_loss"
        if position.stop_price is not None and low <= position.stop_price:
            return position.stop_price, "stop_loss"
        if position.take_profit_price is not None and high >= position.take_profit_price:
            return position.take_profit_price, "take_profit"
    else:
        if position.stop_price is not None and position.take_profit_price is not None:
            if high >= position.stop_price and low <= position.take_profit_price:
                return position.stop_price, "stop_loss"
        if position.stop_price is not None and high >= position.stop_price:
            return position.stop_price, "stop_loss"
        if position.take_profit_price is not None and low <= position.take_profit_price:
            return position.take_profit_price, "take_profit"

    if bool(exit_signal):
        return open_price, "signal"
    return None


def _evaluate_rule(rule: CompiledRule | None, frame: pd.DataFrame) -> pd.Series:
    if rule is None:
        return pd.Series(False, index=frame.index)
    if rule.operator == "and":
        series = [_evaluate_rule(child, frame) for child in rule.conditions]
        result = series[0]
        for item in series[1:]:
            result = result & item
        return result.fillna(False)
    if rule.operator == "or":
        series = [_evaluate_rule(child, frame) for child in rule.conditions]
        result = series[0]
        for item in series[1:]:
            result = result | item
        return result.fillna(False)
    left = _resolve_operand(rule.left, frame)
    right = _resolve_operand(rule.right, frame)
    if rule.operator == "lt":
        return (left < right).fillna(False)
    if rule.operator == "lte":
        return (left <= right).fillna(False)
    if rule.operator == "gt":
        return (left > right).fillna(False)
    if rule.operator == "gte":
        return (left >= right).fillna(False)
    if rule.operator == "crosses_above":
        return ((left.shift(1) <= right.shift(1)) & (left > right)).fillna(False)
    if rule.operator == "crosses_below":
        return ((left.shift(1) >= right.shift(1)) & (left < right)).fillna(False)
    raise ValueError(f"Unsupported rule operator: {rule.operator}")


def _resolve_operand(operand, frame: pd.DataFrame) -> pd.Series:
    if operand.kind == "indicator":
        return frame[operand.value]
    return pd.Series(float(operand.value), index=frame.index)


def _apply_entry_costs(direction: str, price: float, slippage_bps: float) -> float:
    factor = slippage_bps / 10_000
    if direction == "long":
        return price * (1 + factor)
    return price * (1 - factor)


def _apply_exit_costs(direction: str, price: float, slippage_bps: float) -> float:
    factor = slippage_bps / 10_000
    if direction == "long":
        return price * (1 - factor)
    return price * (1 + factor)
