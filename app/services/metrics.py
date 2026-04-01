"""Metric helpers for backtest summaries."""
from __future__ import annotations


def summarize_trades(trades: list[dict], equity_curve: list[dict], initial_capital: float, final_equity: float) -> dict:
    trade_count = len(trades)
    wins = [trade for trade in trades if trade["pnl"] > 0]
    losses = [trade for trade in trades if trade["pnl"] < 0]
    win_rate = (len(wins) / trade_count * 100) if trade_count else 0.0
    gross_profit = sum(trade["pnl"] for trade in wins)
    gross_loss = abs(sum(trade["pnl"] for trade in losses))
    profit_factor = gross_profit / gross_loss if gross_loss else gross_profit or 0.0
    avg_win = gross_profit / len(wins) if wins else 0.0
    avg_loss = (sum(trade["pnl"] for trade in losses) / len(losses)) if losses else 0.0
    expectancy = sum(trade["pnl"] for trade in trades) / trade_count if trade_count else 0.0
    max_drawdown = max((point["drawdown_pct"] for point in equity_curve), default=0.0)
    return {
        "trade_count": trade_count,
        "win_rate": round(win_rate, 2),
        "total_pnl": round(final_equity - initial_capital, 2),
        "net_return_pct": round(((final_equity - initial_capital) / initial_capital) * 100, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "profit_factor": round(profit_factor, 2),
        "average_win": round(avg_win, 2),
        "average_loss": round(avg_loss, 2),
        "expectancy": round(expectancy, 2),
        "longest_win_streak": _longest_streak(trades, True),
        "longest_loss_streak": _longest_streak(trades, False),
    }


def _longest_streak(trades: list[dict], is_win: bool) -> int:
    longest = current = 0
    for trade in trades:
        passed = trade["pnl"] > 0 if is_win else trade["pnl"] < 0
        if passed:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest
