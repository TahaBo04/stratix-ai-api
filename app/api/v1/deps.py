"""Shared API dependencies."""
from __future__ import annotations

from fastapi import Header, HTTPException

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.repositories.users import ensure_demo_user, ensure_guest_user, get_user_by_id


def get_current_user(
    authorization: str | None = Header(default=None),
    guest_session_id: str | None = Header(default=None, alias="x-stratix-guest-id"),
) -> dict:
    settings = get_settings()
    if not authorization:
        if guest_session_id:
            return ensure_guest_user(guest_session_id)
        return ensure_demo_user(settings.default_demo_user_email, settings.default_demo_user_password)
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = get_user_by_id(payload.get("sub", ""))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user
