"""Strategy repository helpers."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from app.core.database import get_connection


def create_strategy(user_id: str, name: str, raw_prompt: str, status: str) -> dict:
    payload = {
        "id": str(uuid4()),
        "user_id": user_id,
        "name": name,
        "raw_prompt": raw_prompt,
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO strategies (id, user_id, name, raw_prompt, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (payload["id"], payload["user_id"], payload["name"], payload["raw_prompt"], payload["status"], payload["created_at"]),
        )
    return payload


def create_strategy_version(strategy_id: str, version_no: int, spec: dict, compiler_version: str, prompt_version: str, generated_python: str, assumptions: list[str]) -> dict:
    payload = {
        "id": str(uuid4()),
        "strategy_id": strategy_id,
        "version_no": version_no,
        "spec_json": json.dumps(spec),
        "compiler_version": compiler_version,
        "prompt_version": prompt_version,
        "generated_python": generated_python,
        "assumptions_json": json.dumps(assumptions),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO strategy_versions (id, strategy_id, version_no, spec_json, compiler_version, prompt_version, generated_python, assumptions_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["id"],
                payload["strategy_id"],
                payload["version_no"],
                payload["spec_json"],
                payload["compiler_version"],
                payload["prompt_version"],
                payload["generated_python"],
                payload["assumptions_json"],
                payload["created_at"],
            ),
        )
    return {
        **payload,
        "spec_json": spec,
        "assumptions_json": assumptions,
    }


def update_strategy(strategy_id: str, *, name: str | None = None, raw_prompt: str | None = None, status: str | None = None) -> dict | None:
    current = get_strategy(strategy_id)
    if current is None:
        return None
    current["name"] = name or current["name"]
    current["raw_prompt"] = raw_prompt or current["raw_prompt"]
    current["status"] = status or current["status"]
    with get_connection() as conn:
        conn.execute(
            "UPDATE strategies SET name = ?, raw_prompt = ?, status = ? WHERE id = ?",
            (current["name"], current["raw_prompt"], current["status"], strategy_id),
        )
    return current


def get_strategy(strategy_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM strategies WHERE id = ?", (strategy_id,)).fetchone()
    return dict(row) if row else None


def get_latest_version(strategy_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM strategy_versions WHERE strategy_id = ? ORDER BY version_no DESC LIMIT 1",
            (strategy_id,),
        ).fetchone()
    return _decode_version(row)


def get_version(version_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM strategy_versions WHERE id = ?", (version_id,)).fetchone()
    return _decode_version(row)


def next_version_number(strategy_id: str) -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COALESCE(MAX(version_no), 0) AS version_no FROM strategy_versions WHERE strategy_id = ?", (strategy_id,)).fetchone()
    return int(row["version_no"]) + 1


def list_strategy_history(user_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM strategies WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _decode_version(row) -> dict | None:
    if row is None:
        return None
    payload = dict(row)
    payload["spec_json"] = json.loads(payload["spec_json"])
    payload["assumptions_json"] = json.loads(payload["assumptions_json"])
    return payload
