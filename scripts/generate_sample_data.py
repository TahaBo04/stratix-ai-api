"""Generate demo OHLCV datasets for STRATIX AI without external dependencies."""
from __future__ import annotations

import csv
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "datasets" / "bars"
OUT_DIR.mkdir(parents=True, exist_ok=True)

STEP_MAP = {
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}

TIMEFRAME_CONFIG = {
    "5m": 600,
    "15m": 600,
    "1h": 720,
    "4h": 540,
    "1d": 400,
}

ASSET_CONFIG = [
    ("BTCUSDT", 32000.0, 0.012),
    ("ETHUSDT", 1800.0, 0.014),
    ("SOLUSDT", 90.0, 0.020),
    ("BNBUSDT", 400.0, 0.010),
    ("EURUSD", 1.09, 0.0025),
    ("GBPUSD", 1.27, 0.0030),
    ("USDJPY", 149.0, 0.0035),
    ("XAUUSD", 2050.0, 0.0040),
]


def build_rows(symbol: str, start_price: float, timeframe: str, periods: int, volatility: float) -> list[dict[str, str | float]]:
    current = datetime(2024, 1, 1, tzinfo=timezone.utc)
    price = start_price
    step = STEP_MAP[timeframe]
    drift = 0.0003 if symbol.endswith("USDT") else 0.0
    rows: list[dict[str, str | float]] = []

    for idx in range(periods):
        cycle = math.sin(idx / 11) * volatility * 0.8
        swing = math.cos(idx / 5) * volatility * 0.3
        pct_change = drift + cycle + swing
        open_price = price
        close_price = max(open_price * (1 + pct_change), 0.0001)
        high = max(open_price, close_price) * (1 + abs(cycle) * 0.6 + 0.001)
        low = min(open_price, close_price) * (1 - abs(swing) * 0.6 - 0.001)
        volume = abs(math.sin(idx / 7) * 900 + 1200)
        rows.append(
            {
                "timestamp": current.isoformat(),
                "open": round(open_price, 6),
                "high": round(high, 6),
                "low": round(max(low, 0.0001), 6),
                "close": round(close_price, 6),
                "volume": round(volume, 2),
            }
        )
        current += step
        price = close_price
    return rows


def main() -> None:
    fieldnames = ["timestamp", "open", "high", "low", "close", "volume"]
    for symbol, start_price, volatility in ASSET_CONFIG:
        for timeframe, periods in TIMEFRAME_CONFIG.items():
            path = OUT_DIR / f"{symbol}_{timeframe}.csv"
            rows = build_rows(symbol, start_price, timeframe, periods, volatility)
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)


if __name__ == "__main__":
    main()
