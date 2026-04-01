"""Authentication routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.security import create_access_token, hash_password, verify_password
from app.repositories.users import create_user, get_user_by_email
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse


router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
def register(payload: RegisterRequest) -> TokenResponse:
    existing = get_user_by_email(payload.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = create_user(
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
    )
    token = create_access_token({"sub": user["id"], "email": user["email"]})
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    user = get_user_by_email(payload.email)
    if user is None or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": user["id"], "email": user["email"]})
    return TokenResponse(access_token=token)
