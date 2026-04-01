"""Backtest repository helpers."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from app.core.database import get_connection


def create_run(strategy_version_id: str, *, asset_symbol: str, asset_class: str, market: str, timeframe: str, date_start: str, date_end: str, initial_capital: float, fees_bps: float, slippage_bps: float) -> dict:
    payload = {
        "id": str(uuid4()),
        "strategy_version_id": strategy_version_id,
        "status": "queued",
        "asset_symbol": asset_symbol,
        "asset_class": asset_class,
        "market": market,
        "timeframe": timeframe,
        "date_start": date_start,
        "date_end": date_end,
        "initial_capital": initial_capital,
        "fees_bps": fees_bps,
        "slippage_bps": slippage_bps,
        "summary_json": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "started_at": None,
        "completed_at": None,
    }
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO backtest_runs (id, strategy_version_id, status, asset_symbol, asset_class, market, timeframe, date_start, date_end, initial_capital, fees_bps, slippage_bps, summary_json, created_at, started_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["id"],
                payload["strategy_version_id"],
                payload["status"],
                payload["asset_symbol"],
                payload["asset_class"],
                payload["market"],
                payload["timeframe"],
                payload["date_start"],
                payload["date_end"],
                payload["initial_capital"],
                payload["fees_bps"],
                payload["slippage_bps"],
                payload["summary_json"],
                payload["created_at"],
                payload["started_at"],
                payload["completed_at"],
            ),
        )
    return payload


def update_run_status(run_id: str, status: str, error_message: str | None = None) -> None:
    started_at = datetime.now(timezone.utc).isoformat() if status == "running" else None
    completed_at = datetime.now(timezone.utc).isoformat() if status in {"completed", "failed"} else None
    with get_connection() as conn:
        if started_at:
            conn.execute("UPDATE backtest_runs SET status = ?, started_at = ? WHERE id = ?", (status, started_at, run_id))
        elif completed_at:
            conn.execute("UPDATE backtest_runs SET status = ?, completed_at = ? WHERE id = ?", (status, completed_at, run_id))
        else:
            conn.execute("UPDATE backtest_runs SET status = ? WHERE id = ?", (status, run_id))
    if error_message is not None:
        create_job_log(job_type="backtest", entity_id=run_id, status=status, error_message=error_message)


def save_run_results(run_id: str, summary: dict, trades: list[dict], equity_curve: list[dict]) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE backtest_runs SET summary_json = ?, status = ?, completed_at = ? WHERE id = ?", (json.dumps(summary), "completed", datetime.now(timezone.utc).isoformat(), run_id))
        conn.execute("DELETE FROM backtest_trades WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM equity_points WHERE run_id = ?", (run_id,))
        for trade in trades:
            conn.execute(
                """
                INSERT INTO backtest_trades (id, run_id, side, entry_time, entry_price, exit_time, exit_price, qty, pnl, pnl_pct, exit_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade["id"],
                    run_id,
                    trade["side"],
                    trade["entry_time"],
                    trade["entry_price"],
                    trade["exit_time"],
                    trade["exit_price"],
                    trade["qty"],
                    trade["pnl"],
                    trade["pnl_pct"],
                    trade["exit_reason"],
                ),
            )
        for idx, point in enumerate(equity_curve, start=1):
            conn.execute(
                "INSERT INTO equity_points (id, run_id, timestamp, equity, drawdown_pct) VALUES (?, ?, ?, ?, ?)",
                (f"{run_id}_eq_{idx}", run_id, point["timestamp"], point["equity"], point["drawdown_pct"]),
            )


def get_run(run_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM backtest_runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        return None
    payload = dict(row)
    payload["summary_json"] = json.loads(payload["summary_json"]) if payload["summary_json"] else {}
    return payload


def get_trades(run_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM backtest_trades WHERE run_id = ? ORDER BY entry_time ASC", (run_id,)).fetchall()
    return [dict(row) for row in rows]


def get_equity_curve(run_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM equity_points WHERE run_id = ? ORDER BY timestamp ASC", (run_id,)).fetchall()
    return [dict(row) for row in rows]


def list_history(user_id: str) -> list[dict]:
    query = """
        SELECT s.id AS strategy_id,
               s.name AS strategy_name,
               r.id AS run_id,
               r.status AS status,
               r.created_at AS created_at,
               r.timeframe AS timeframe,
               r.asset_symbol AS asset_symbol,
               r.summary_json AS summary_json
        FROM backtest_runs r
        JOIN strategy_versions sv ON r.strategy_version_id = sv.id
        JOIN strategies s ON sv.strategy_id = s.id
        WHERE s.user_id = ?
        ORDER BY r.created_at DESC
    """
    with get_connection() as conn:
        rows = conn.execute(query, (user_id,)).fetchall()
    items = []
    for row in rows:
        payload = dict(row)
        payload["summary_json"] = json.loads(payload["summary_json"]) if payload["summary_json"] else {}
        items.append(payload)
    return items


def create_job_log(job_type: str, entity_id: str, status: str, error_message: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO job_logs (id, job_type, entity_id, status, error_message, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid4()), job_type, entity_id, status, error_message, datetime.now(timezone.utc).isoformat()),
        )


def list_job_logs(limit: int = 50) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM job_logs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(row) for row in rows]
