"""Indicator calculations for the constrained backtest engine."""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_indicator(frame: pd.DataFrame, indicator: dict) -> pd.Series:
    indicator_type = indicator["type"]
    source = indicator.get("source", "close")
    if indicator_type == "SMA":
        return frame[source].rolling(window=indicator.get("length", 14), min_periods=indicator.get("length", 14)).mean()
    if indicator_type == "EMA":
        return frame[source].ewm(span=indicator.get("length", 14), adjust=False).mean()
    if indicator_type == "RSI":
        return _rsi(frame[source], indicator.get("length", 14))
    if indicator_type == "MACD":
        fast = frame[source].ewm(span=indicator.get("fast_length", 12), adjust=False).mean()
        slow = frame[source].ewm(span=indicator.get("slow_length", 26), adjust=False).mean()
        macd = fast - slow
        signal = macd.ewm(span=indicator.get("signal_length", 9), adjust=False).mean()
        output = indicator.get("output", "macd")
        if output == "signal":
            return signal
        if output == "histogram":
            return macd - signal
        return macd
    if indicator_type == "BOLLINGER":
        length = indicator.get("length", 20)
        std_dev = indicator.get("std_dev", 2.0)
        middle = frame[source].rolling(window=length, min_periods=length).mean()
        std = frame[source].rolling(window=length, min_periods=length).std()
        output = indicator.get("output", "middle")
        if output == "upper":
            return middle + std * std_dev
        if output == "lower":
            return middle - std * std_dev
        return middle
    if indicator_type == "ATR":
        return _atr(frame, indicator.get("length", 14))
    raise ValueError(f"Unsupported indicator type: {indicator_type}")


def _rsi(series: pd.Series, length: int) -> pd.Series:
    delta = series.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    avg_gain = gains.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(frame: pd.DataFrame, length: int) -> pd.Series:
    high_low = frame["high"] - frame["low"]
    high_close = (frame["high"] - frame["close"].shift()).abs()
    low_close = (frame["low"] - frame["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=length, min_periods=length).mean()
