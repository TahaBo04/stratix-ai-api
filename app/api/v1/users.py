"""User routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1.deps import get_current_user
from app.schemas.auth import UserResponse
from app.schemas.preferences import UpdateUserPreferencesRequest, UserPreferencesResponse
from app.repositories.users import get_user_preferences, update_user_preferences


router = APIRouter(tags=["users"])


@router.get("/v1/me", response_model=UserResponse)
def me(current_user: dict = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.get("/v1/me/preferences", response_model=UserPreferencesResponse)
def me_preferences(current_user: dict = Depends(get_current_user)) -> UserPreferencesResponse:
    return UserPreferencesResponse.model_validate(get_user_preferences(current_user["id"]))


@router.patch("/v1/me/preferences", response_model=UserPreferencesResponse)
def update_me_preferences(payload: UpdateUserPreferencesRequest, current_user: dict = Depends(get_current_user)) -> UserPreferencesResponse:
    preferences = update_user_preferences(
        current_user["id"],
        price_chart_type=payload.price_chart_type,
    )
    return UserPreferencesResponse.model_validate(preferences)
