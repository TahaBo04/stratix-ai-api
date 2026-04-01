"""User preference schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


PriceChartType = Literal["candles", "line"]


class UserPreferencesResponse(BaseModel):
    user_id: str
    price_chart_type: PriceChartType = "candles"
    created_at: datetime
    updated_at: datetime


class UpdateUserPreferencesRequest(BaseModel):
    price_chart_type: PriceChartType | None = None
