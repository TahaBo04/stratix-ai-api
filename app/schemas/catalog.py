"""Catalog schemas."""
from __future__ import annotations

from pydantic import BaseModel


class IndicatorCatalogItem(BaseModel):
    type: str
    label: str
    description: str
    params: list[str]
    outputs: list[str]


class AssetCatalogItem(BaseModel):
    asset_class: str
    market: str
    symbol: str
    provider_symbol: str
    base_currency: str
    quote_currency: str
    supported_timeframes: list[str]


class CatalogResponse(BaseModel):
    indicators: list[IndicatorCatalogItem]
    operators: list[str]


class AssetCatalogResponse(BaseModel):
    assets: list[AssetCatalogItem]
