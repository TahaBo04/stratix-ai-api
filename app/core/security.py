"""Security helpers for simple local authentication."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from app.core.config import get_settings


def hash_password(password: str, salt: str | None = None) -> str:
    actual_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), actual_salt.encode("utf-8"), 100_000)
    return f"{actual_salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    salt, _digest = stored_hash.split("$", 1)
    return hmac.compare_digest(hash_password(password, salt), stored_hash)


def create_access_token(payload: dict[str, Any], expires_in_seconds: int = 60 * 60 * 12) -> str:
    body = {**payload, "exp": int(time.time()) + expires_in_seconds}
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(get_settings().secret_key.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    token = base64.urlsafe_b64encode(raw).decode("utf-8")
    return f"{token}.{signature}"


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        encoded, signature = token.split(".", 1)
        raw = base64.urlsafe_b64decode(encoded.encode("utf-8"))
        expected = hmac.new(get_settings().secret_key.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(raw.decode("utf-8"))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None
