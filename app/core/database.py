"""SQLite helpers used by the local MVP."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.core.config import get_settings


SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        username TEXT NOT NULL DEFAULT '',
        full_name TEXT,
        role TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_preferences (
        user_id TEXT PRIMARY KEY,
        price_chart_type TEXT NOT NULL DEFAULT 'candles',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS strategies (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        name TEXT NOT NULL,
        raw_prompt TEXT NOT NULL,
        service_tier TEXT NOT NULL DEFAULT 'simple',
        status TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_versions (
        id TEXT PRIMARY KEY,
        strategy_id TEXT NOT NULL,
        version_no INTEGER NOT NULL,
        spec_json TEXT NOT NULL,
        compiler_version TEXT NOT NULL,
        prompt_version TEXT NOT NULL,
        generated_python TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS backtest_runs (
        id TEXT PRIMARY KEY,
        strategy_version_id TEXT NOT NULL,
        status TEXT NOT NULL,
        error_message TEXT,
        asset_symbol TEXT NOT NULL,
        asset_class TEXT NOT NULL,
        market TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        date_start TEXT NOT NULL,
        date_end TEXT NOT NULL,
        initial_capital REAL NOT NULL,
        fees_bps REAL NOT NULL,
        slippage_bps REAL NOT NULL,
        summary_json TEXT,
        created_at TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS backtest_trades (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        side TEXT NOT NULL,
        entry_time TEXT NOT NULL,
        entry_price REAL NOT NULL,
        exit_time TEXT NOT NULL,
        exit_price REAL NOT NULL,
        qty REAL NOT NULL,
        pnl REAL NOT NULL,
        pnl_pct REAL NOT NULL,
        exit_reason TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS equity_points (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        equity REAL NOT NULL,
        drawdown_pct REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_traces (
        id TEXT PRIMARY KEY,
        strategy_version_id TEXT,
        model TEXT NOT NULL,
        request_json TEXT NOT NULL,
        response_json TEXT NOT NULL,
        validation_errors_json TEXT NOT NULL,
        token_usage_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS job_logs (
        id TEXT PRIMARY KEY,
        job_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        status TEXT NOT NULL,
        error_message TEXT,
        created_at TEXT NOT NULL
    )
    """,
]


def _db_path() -> Path:
    return get_settings().database_file


def init_db() -> None:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        for statement in SCHEMA:
            conn.execute(statement)
        _ensure_user_columns(conn)
        _ensure_user_preference_columns(conn)
        _ensure_strategy_columns(conn)
        _ensure_backtest_run_columns(conn)
        conn.commit()


@contextmanager
def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _ensure_user_columns(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "username" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN username TEXT NOT NULL DEFAULT ''")
    if "full_name" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN full_name TEXT")
    conn.execute(
        """
        UPDATE users
        SET username = lower(
            CASE
                WHEN instr(email, '@') > 1 THEN substr(email, 1, instr(email, '@') - 1)
                ELSE email
            END
        )
        WHERE username IS NULL OR username = ''
        """
    )


def _ensure_user_preference_columns(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(user_preferences)").fetchall()}
    if not columns:
        return
    if "price_chart_type" not in columns:
        conn.execute("ALTER TABLE user_preferences ADD COLUMN price_chart_type TEXT NOT NULL DEFAULT 'candles'")
    if "created_at" not in columns:
        conn.execute("ALTER TABLE user_preferences ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
    if "updated_at" not in columns:
        conn.execute("ALTER TABLE user_preferences ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")


def _ensure_backtest_run_columns(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(backtest_runs)").fetchall()}
    if not columns:
        return
    if "error_message" not in columns:
        conn.execute("ALTER TABLE backtest_runs ADD COLUMN error_message TEXT")


def _ensure_strategy_columns(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(strategies)").fetchall()}
    if not columns:
        return
    if "service_tier" not in columns:
        conn.execute("ALTER TABLE strategies ADD COLUMN service_tier TEXT NOT NULL DEFAULT 'simple'")
