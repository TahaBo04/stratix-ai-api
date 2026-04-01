"""Market data access for local seed datasets."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.core.config import get_settings
from app.services.catalog import ASSETS


class DatasetNotFoundError(FileNotFoundError):
    """Raised when the requested dataset is unavailable."""


def dataset_path(symbol: str, timeframe: str) -> Path:
    return get_settings().datasets_root / "bars" / f"{symbol.upper()}_{timeframe}.csv"


def load_bars(symbol: str, timeframe: str, start: str, end: str) -> pd.DataFrame:
    path = dataset_path(symbol, timeframe)
    if not path.exists():
        raise DatasetNotFoundError(f"Missing dataset for {symbol} {timeframe}: {path}")
    frame = pd.read_csv(path)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")
    if len(end) == 10:
        end_ts = end_ts + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    filtered = frame[(frame["timestamp"] >= start_ts) & (frame["timestamp"] <= end_ts)].copy()
    if filtered.empty:
        raise DatasetNotFoundError(f"No data found for {symbol} between {start} and {end}")
    return filtered.reset_index(drop=True)


def available_assets(query: str | None = None) -> list[dict]:
    if not query:
        return [asset.model_dump() for asset in ASSETS]
    token = query.upper().strip()
    return [asset.model_dump() for asset in ASSETS if token in asset.symbol or token in asset.provider_symbol]
