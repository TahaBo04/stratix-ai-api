"""Catalog routes."""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas.catalog import AssetCatalogResponse, CatalogResponse
from app.services.catalog import INDICATORS, SUPPORTED_OPERATORS
from app.services.market_data import available_assets


router = APIRouter(prefix="/v1/catalog", tags=["catalog"])


@router.get("/indicators", response_model=CatalogResponse)
def get_catalog() -> CatalogResponse:
    return CatalogResponse(indicators=INDICATORS, operators=SUPPORTED_OPERATORS)


@router.get("/assets", response_model=AssetCatalogResponse)
def get_assets(query: str | None = Query(default=None)) -> AssetCatalogResponse:
    return AssetCatalogResponse(assets=available_assets(query))
