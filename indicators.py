"""
indicators.py
-------------
Standard technical-analysis functions used across timeframes:
EMA, RSI, VWAP-relative positioning, pivot support/resistance,
and simple trend classification per timeframe.

Every function takes/returns plain pandas Series or floats so it can
be reused for 5m / 15m / 30m / daily data alike.
"""

from __future__ import annotations
from typing import Optional
import pandas as pd
import numpy as np


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(window=length).mean()


def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50.0)  # neutral when undefined (e.g. no data yet)


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def classic_pivot_levels(prev_high: float, prev_low: float, prev_close: float) -> dict:
    """Standard floor-trader pivot point formula."""
    pivot = (prev_high + prev_low + prev_close) / 3
    r1 = (2 * pivot) - prev_low
    s1 = (2 * pivot) - prev_high
    r2 = pivot + (prev_high - prev_low)
    s2 = pivot - (prev_high - prev_low)
    r3 = prev_high + 2 * (pivot - prev_low)
    s3 = prev_low - 2 * (prev_high - pivot)
    return {
        "pivot": round(pivot, 2),
        "r1": round(r1, 2), "r2": round(r2, 2), "r3": round(r3, 2),
        "s1": round(s1, 2), "s2": round(s2, 2), "s3": round(s3, 2),
    }


def classify_trend(price: float, ema20: float, ema50: float, rsi_val: float) -> tuple[str, int]:
    """
    Simple rule-based trend + confidence classifier.
    Returns (label, confidence_percent). This is a heuristic, not a
    predictive model -- treat the confidence score as illustrative.
    """
    score = 0
    if price > ema20:
        score += 1
    if price > ema50:
        score += 1
    if ema20 > ema50:
        score += 1
    if rsi_val > 55:
        score += 1
    elif rsi_val < 45:
        score -= 1

    if score >= 3:
        return "Bullish", min(80, 55 + score * 6)
    elif score <= -1:
        return "Bearish", min(80, 55 + abs(score) * 6)
    elif score == 2:
        return "Mild Bullish", 55
    elif score == -0:
        return "Neutral", 50
    else:
        return "Mild Bearish", 52


def gap_structure(open_price: float, previous_close: float) -> dict:
    gap_pct = ((open_price - previous_close) / previous_close) * 100 if previous_close else 0.0
    if gap_pct > 0.3:
        label = "Gap Up"
    elif gap_pct < -0.3:
        label = "Gap Down"
    else:
        label = "Flat / No Significant Gap"
    return {"gap_pct": round(gap_pct, 2), "label": label}


def timeframe_indicator_bundle(df: pd.DataFrame, price_col: str = "close") -> Optional[dict]:
    """
    Given an OHLCV DataFrame for a single timeframe (5m/15m/30m/1d),
    compute EMA20, EMA50, RSI14, and latest MACD histogram value.
    Returns None if there isn't enough data for a stable EMA50.
    """
    if df is None or df.empty or len(df) < 20:
        return None
    close = df[price_col]
    ema20_s = ema(close, 20)
    ema50_s = ema(close, 50) if len(df) >= 50 else ema(close, min(len(df) - 1, 20))
    rsi_s = rsi(close, 14)
    macd_line, signal_line, hist = macd(close)

    last_price = float(close.iloc[-1])
    last_ema20 = float(ema20_s.iloc[-1])
    last_ema50 = float(ema50_s.iloc[-1])
    last_rsi = float(rsi_s.iloc[-1])
    last_hist = float(hist.iloc[-1]) if not hist.empty else 0.0

    trend_label, confidence = classify_trend(last_price, last_ema20, last_ema50, last_rsi)

    return {
        "last_price": round(last_price, 2),
        "ema20": round(last_ema20, 2),
        "ema50": round(last_ema50, 2),
        "rsi14": round(last_rsi, 2),
        "macd_hist": round(last_hist, 2),
        "trend": trend_label,
        "confidence_pct": confidence,
    }
