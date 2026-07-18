"""
sentiment.py
------------
Turns technical + breadth + flow inputs into:
  1. A market sentiment classification (Bullish ... Bearish)
  2. Up/Down/Sideways probability estimates for the session

IMPORTANT: This is a transparent, rule-based heuristic scorer for
educational purposes -- NOT a statistically validated predictive
model, and NOT trading advice. Weights are simple and adjustable.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class SentimentInputs:
    price_vs_vwap: Optional[float] = None       # % price is above/below VWAP
    trend_5m: str = "Neutral"
    trend_15m: str = "Neutral"
    trend_30m: str = "Neutral"
    rsi_daily: Optional[float] = None
    macd_hist_daily: Optional[float] = None
    advances: Optional[int] = None
    declines: Optional[int] = None
    fii_net_cr: Optional[float] = None           # crores; negative = selling
    dii_net_cr: Optional[float] = None
    india_vix: Optional[float] = None
    vix_change_pct: Optional[float] = None


SENTIMENT_LABELS = ["Bearish", "Mild Bearish", "Neutral", "Mild Bullish", "Bullish"]


def score_sentiment(inp: SentimentInputs) -> dict:
    """
    Produces a weighted score in roughly [-5, +5], then maps it to a
    5-point sentiment scale with a confidence percentage.
    """
    score = 0.0
    reasons = []

    trend_map = {"Bullish": 1, "Mild Bullish": 0.5, "Neutral": 0,
                 "Mild Bearish": -0.5, "Bearish": -1}
    for label, tf in [(inp.trend_5m, "5-min"), (inp.trend_15m, "15-min"), (inp.trend_30m, "30-min")]:
        contribution = trend_map.get(label, 0)
        score += contribution
        if contribution != 0:
            reasons.append(f"{tf} trend reading: {label}")

    if inp.price_vs_vwap is not None:
        if inp.price_vs_vwap > 0.05:
            score += 1
            reasons.append("Price trading above VWAP")
        elif inp.price_vs_vwap < -0.05:
            score -= 1
            reasons.append("Price trading below VWAP")

    if inp.rsi_daily is not None:
        if inp.rsi_daily > 60:
            score += 0.5
            reasons.append(f"Daily RSI elevated at {inp.rsi_daily:.1f}")
        elif inp.rsi_daily < 40:
            score -= 0.5
            reasons.append(f"Daily RSI weak at {inp.rsi_daily:.1f}")

    if inp.macd_hist_daily is not None:
        if inp.macd_hist_daily > 0:
            score += 0.5
            reasons.append("MACD histogram positive")
        else:
            score -= 0.5
            reasons.append("MACD histogram negative")

    if inp.advances is not None and inp.declines is not None and (inp.advances + inp.declines) > 0:
        ad_ratio = inp.advances / max(inp.declines, 1)
        if ad_ratio > 1.2:
            score += 1
            reasons.append(f"Positive market breadth (A/D ratio {ad_ratio:.2f})")
        elif ad_ratio < 0.83:
            score -= 1
            reasons.append(f"Weak market breadth (A/D ratio {ad_ratio:.2f})")

    if inp.fii_net_cr is not None:
        if inp.fii_net_cr < -1000:
            score -= 0.5
            reasons.append(f"Notable FII selling (₹{inp.fii_net_cr:.0f} Cr)")
        elif inp.fii_net_cr > 1000:
            score += 0.5
            reasons.append(f"Notable FII buying (₹{inp.fii_net_cr:.0f} Cr)")

    if inp.dii_net_cr is not None and inp.dii_net_cr > 500:
        score += 0.5
        reasons.append(f"DII buying support (₹{inp.dii_net_cr:.0f} Cr)")

    if inp.vix_change_pct is not None:
        if inp.vix_change_pct < -3:
            score += 0.3
            reasons.append("India VIX easing — lower fear premium")
        elif inp.vix_change_pct > 5:
            score -= 0.5
            reasons.append("India VIX spiking — rising hedging demand")

    # Map score to label
    if score >= 2.5:
        label = "Bullish"
    elif score >= 1:
        label = "Mild Bullish"
    elif score > -1:
        label = "Neutral"
    elif score > -2.5:
        label = "Mild Bearish"
    else:
        label = "Bearish"

    confidence = min(85, 50 + abs(score) * 6)

    return {
        "score": round(score, 2),
        "label": label,
        "confidence_pct": round(confidence),
        "reasons": reasons,
    }


def estimate_probabilities(sentiment_score: float, vix: Optional[float] = None) -> dict:
    """
    Converts the sentiment score (~ -5..+5) into Up / Down / Sideways
    probabilities that always sum to 100.

    Higher |score| -> more directional conviction, less "sideways" mass.
    Higher VIX -> more probability mass shifted into "sideways/volatile"
    to reflect wider expected dispersion.
    """
    base_side = 30.0
    if vix is not None:
        if vix > 18:
            base_side = 40.0
        elif vix < 13:
            base_side = 25.0

    directional_mass = 100 - base_side
    # sigmoid-ish split of directional mass between up/down based on score
    score = max(-5, min(5, sentiment_score))
    up_share = 0.5 + (score / 10)   # score=+5 -> 1.0 (all directional mass up), score=-5 -> 0.0
    up_share = max(0.0, min(1.0, up_share))

    up = round(directional_mass * up_share)
    down = round(directional_mass * (1 - up_share))
    sideways = 100 - up - down

    return {"up_pct": up, "down_pct": down, "sideways_pct": sideways}
