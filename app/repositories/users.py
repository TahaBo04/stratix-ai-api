"""User repository helpers."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import uuid4

from app.core.database import get_connection
from app.core.security import hash_password

DEFAULT_USER_PREFERENCES = {
    "price_chart_type": "candles",
}


def derive_username(email: str) -> str:
    local_part = email.split("@", 1)[0].strip().lower()
    return local_part or "stratix-user"


def create_user(email: str, password_hash: str, role: str = "user", username: str | None = None, full_name: str | None = None) -> dict:
    payload = {
        "id": str(uuid4()),
        "email": email.lower(),
        "password_hash": password_hash,
        "username": (username or derive_username(email)).strip().lower(),
        "full_name": full_name.strip() if full_name else None,
        "role": role,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO users (id, email, password_hash, username, full_name, role, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                payload["id"],
                payload["email"],
                payload["password_hash"],
                payload["username"],
                payload["full_name"],
                payload["role"],
                payload["created_at"],
            ),
        )
    return payload


def get_user_by_email(email: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_user_preferences(user_id: str) -> dict:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM user_preferences WHERE user_id = ?", (user_id,)).fetchone()
    if row:
        return dict(row)
    timestamp = datetime.now(timezone.utc).isoformat()
    payload = {
        "user_id": user_id,
        "price_chart_type": DEFAULT_USER_PREFERENCES["price_chart_type"],
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO user_preferences (user_id, price_chart_type, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (payload["user_id"], payload["price_chart_type"], payload["created_at"], payload["updated_at"]),
        )
        row = conn.execute("SELECT * FROM user_preferences WHERE user_id = ?", (user_id,)).fetchone()
    return dict(row) if row else payload


def update_user_preferences(user_id: str, *, price_chart_type: str | None = None) -> dict:
    current = get_user_preferences(user_id)
    next_price_chart_type = price_chart_type or current["price_chart_type"]
    updated_at = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO user_preferences (user_id, price_chart_type, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                price_chart_type = excluded.price_chart_type,
                updated_at = excluded.updated_at
            """,
            (user_id, next_price_chart_type, current["created_at"], updated_at),
        )
        row = conn.execute("SELECT * FROM user_preferences WHERE user_id = ?", (user_id,)).fetchone()
    return dict(row) if row else {
        "user_id": user_id,
        "price_chart_type": next_price_chart_type,
        "created_at": current["created_at"],
        "updated_at": updated_at,
    }


def ensure_demo_user(email: str, password: str) -> dict:
    existing = get_user_by_email(email)
    if existing:
        return existing
    return create_user(email=email, password_hash=hash_password(password), role="demo", full_name="Demo User")


def ensure_guest_user(guest_session_id: str) -> dict:
    digest = hashlib.sha256(guest_session_id.encode("utf-8")).hexdigest()[:24]
    email = f"guest-{digest}@guest.stratix.ai"
    existing = get_user_by_email(email)
    if existing:
        return existing
    return create_user(
        email=email,
        password_hash=hash_password(guest_session_id),
        role="demo",
        username=f"guest-{digest[:12]}",
        full_name="Guest Workspace",
    )
