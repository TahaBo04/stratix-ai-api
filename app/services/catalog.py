"""Catalogs of supported assets, indicators, and operators."""
from __future__ import annotations

from app.schemas.catalog import AssetCatalogItem, IndicatorCatalogItem


SUPPORTED_OPERATORS = ["lt", "lte", "gt", "gte", "crosses_above", "crosses_below", "and", "or"]
SUPPORTED_TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d"]

INDICATORS = [
    IndicatorCatalogItem(type="RSI", label="RSI", description="Relative Strength Index oscillator.", params=["length", "source"], outputs=["value"]),
    IndicatorCatalogItem(type="SMA", label="SMA", description="Simple moving average.", params=["length", "source"], outputs=["value"]),
    IndicatorCatalogItem(type="EMA", label="EMA", description="Exponential moving average.", params=["length", "source"], outputs=["value"]),
    IndicatorCatalogItem(type="MACD", label="MACD", description="MACD line, signal line, and histogram.", params=["fast_length", "slow_length", "signal_length", "source"], outputs=["macd", "signal", "histogram"]),
    IndicatorCatalogItem(type="BOLLINGER", label="Bollinger Bands", description="Middle, upper, and lower bands.", params=["length", "std_dev", "source"], outputs=["middle", "upper", "lower"]),
    IndicatorCatalogItem(type="ATR", label="ATR", description="Average true range.", params=["length"], outputs=["value"]),
]

ASSETS = [
    AssetCatalogItem(asset_class="crypto", market="binance", symbol="BTCUSDT", provider_symbol="BTC/USDT", base_currency="BTC", quote_currency="USDT", supported_timeframes=SUPPORTED_TIMEFRAMES),
    AssetCatalogItem(asset_class="crypto", market="binance", symbol="ETHUSDT", provider_symbol="ETH/USDT", base_currency="ETH", quote_currency="USDT", supported_timeframes=SUPPORTED_TIMEFRAMES),
    AssetCatalogItem(asset_class="crypto", market="binance", symbol="SOLUSDT", provider_symbol="SOL/USDT", base_currency="SOL", quote_currency="USDT", supported_timeframes=SUPPORTED_TIMEFRAMES),
    AssetCatalogItem(asset_class="crypto", market="binance", symbol="BNBUSDT", provider_symbol="BNB/USDT", base_currency="BNB", quote_currency="USDT", supported_timeframes=SUPPORTED_TIMEFRAMES),
    AssetCatalogItem(asset_class="forex", market="otc", symbol="EURUSD", provider_symbol="EUR/USD", base_currency="EUR", quote_currency="USD", supported_timeframes=SUPPORTED_TIMEFRAMES),
    AssetCatalogItem(asset_class="forex", market="otc", symbol="GBPUSD", provider_symbol="GBP/USD", base_currency="GBP", quote_currency="USD", supported_timeframes=SUPPORTED_TIMEFRAMES),
    AssetCatalogItem(asset_class="forex", market="otc", symbol="USDJPY", provider_symbol="USD/JPY", base_currency="USD", quote_currency="JPY", supported_timeframes=SUPPORTED_TIMEFRAMES),
    AssetCatalogItem(asset_class="commodity", market="otc", symbol="XAUUSD", provider_symbol="XAU/USD", base_currency="XAU", quote_currency="USD", supported_timeframes=SUPPORTED_TIMEFRAMES),
]


def find_asset(symbol: str) -> AssetCatalogItem | None:
    symbol_upper = symbol.upper()
    for asset in ASSETS:
        if asset.symbol == symbol_upper:
            return asset
    return None
