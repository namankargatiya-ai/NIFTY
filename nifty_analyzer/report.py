"""
report.py
---------
Assembles fetched data + computed indicators + sentiment scoring into
the final structured markdown report (same sections as the manual
research template: data snapshot, technical analysis, sentiment,
trend, probabilities, price expectation, ATM option view, time-block
breakdown, risk factors, final summary).
"""

from __future__ import annotations
import datetime as dt
from typing import Optional

from . import indicators as ind
from .sentiment import SentimentInputs, score_sentiment, estimate_probabilities
from .fetch_data import MarketSnapshot


TIME_BLOCKS = [
    ("09:15-10:30", "Opening volatility / gap resolution"),
    ("10:30-12:00", "Mid-morning trend continuation or consolidation"),
    ("12:00-13:30", "Lunch-hour lull, lower volatility typical"),
    ("13:30-15:30", "Afternoon positioning, F&O expiry effects if applicable"),
]

RISK_FACTORS = [
    ("Unexpected macro/geopolitical news", "Moderate"),
    ("RBI policy surprise", "Low-Moderate"),
    ("Global market reversal (US/Asia)", "Moderate"),
    ("Sudden volatility spike (VIX)", "Moderate"),
    ("Banking sector-specific events", "Moderate"),
]


def _fmt(x, nd=2):
    return f"{x:.{nd}f}" if isinstance(x, (int, float)) else "N/A"


def _timeframe_block(df, label: str):
    bundle = ind.timeframe_indicator_bundle(df) if df is not None else None
    if bundle is None:
        return {"trend": "Neutral", "confidence_pct": 50, "detail": f"{label}: insufficient data"}
    return bundle


def generate_report(snapshot: MarketSnapshot,
                     advances: Optional[int] = None,
                     declines: Optional[int] = None,
                     fii_net_cr: Optional[float] = None,
                     dii_net_cr: Optional[float] = None,
                     vix_change_pct: Optional[float] = None) -> str:
    """Build the full markdown report string from a MarketSnapshot."""

    market_open = snapshot.is_market_open_today()
    now = snapshot.fetched_at

    tf5 = _timeframe_block(snapshot.intraday_5m, "5-min")
    tf15 = _timeframe_block(snapshot.intraday_15m, "15-min")
    tf30 = _timeframe_block(snapshot.intraday_30m, "30-min")
    daily = _timeframe_block(snapshot.daily_history, "Daily")

    price_vs_vwap = None
    if snapshot.current_price and snapshot.vwap:
        price_vs_vwap = ((snapshot.current_price - snapshot.vwap) / snapshot.vwap) * 100

    s_inputs = SentimentInputs(
        price_vs_vwap=price_vs_vwap,
        trend_5m=tf5["trend"], trend_15m=tf15["trend"], trend_30m=tf30["trend"],
        rsi_daily=daily.get("rsi14"),
        macd_hist_daily=daily.get("macd_hist"),
        advances=advances, declines=declines,
        fii_net_cr=fii_net_cr, dii_net_cr=dii_net_cr,
        india_vix=snapshot.india_vix, vix_change_pct=vix_change_pct,
    )
    sentiment = score_sentiment(s_inputs)
    probs = estimate_probabilities(sentiment["score"], snapshot.india_vix)

    pivots = {}
    if snapshot.day_high and snapshot.day_low and snapshot.previous_close:
        pivots = ind.classic_pivot_levels(snapshot.day_high, snapshot.day_low, snapshot.previous_close)

    gap = {}
    if snapshot.open_price and snapshot.previous_close:
        gap = ind.gap_structure(snapshot.open_price, snapshot.previous_close)

    atm_strike = None
    if snapshot.current_price:
        atm_strike = round(snapshot.current_price / 50) * 50  # NIFTY strikes are in steps of 50

    call_prob = 50 + (sentiment["score"] * 4)
    put_prob = 100 - call_prob
    call_prob = max(15, min(80, round(call_prob)))
    put_prob = 100 - call_prob

    lines = []
    lines.append(f"# NIFTY 50 Market Research Report")
    lines.append(f"_Generated: {now.strftime('%Y-%m-%d %H:%M:%S')} IST | "
                 f"Market session status: {'LIVE/OPEN (weekday)' if market_open else 'CLOSED (weekend/holiday)'}_\n")

    if not market_open:
        lines.append("> **Note:** Today is a non-trading day. Figures below reflect the "
                      "most recently completed session and current available data, not a live tape.\n")

    lines.append("## 1. Current Market Data")
    lines.append(f"| Metric | Value |\n|---|---|")
    lines.append(f"| Current / Last Price | {_fmt(snapshot.current_price)} |")
    lines.append(f"| Previous Close | {_fmt(snapshot.previous_close)} |")
    lines.append(f"| Open | {_fmt(snapshot.open_price)} |")
    lines.append(f"| Day High | {_fmt(snapshot.day_high)} |")
    lines.append(f"| Day Low | {_fmt(snapshot.day_low)} |")
    lines.append(f"| VWAP (intraday, if available) | {_fmt(snapshot.vwap)} |")
    lines.append(f"| Volume | {_fmt(snapshot.volume, 0)} |")
    lines.append(f"| India VIX | {_fmt(snapshot.india_vix)} |")
    if advances is not None and declines is not None:
        lines.append(f"| Market Breadth (Adv/Dec) | {advances} / {declines} |")
    lines.append("")

    lines.append("## 2. Technical Analysis")
    lines.append("| Timeframe | Trend | Confidence | EMA20 | EMA50 | RSI(14) |")
    lines.append("|---|---|---|---|---|---|")
    for name, tf in [("5-min", tf5), ("15-min", tf15), ("30-min", tf30), ("Daily", daily)]:
        lines.append(f"| {name} | {tf.get('trend','N/A')} | {tf.get('confidence_pct','N/A')}% | "
                     f"{_fmt(tf.get('ema20'))} | {_fmt(tf.get('ema50'))} | {_fmt(tf.get('rsi14'))} |")
    lines.append("")
    if pivots:
        lines.append(f"**Support levels:** S1 {pivots['s1']}, S2 {pivots['s2']}, S3 {pivots['s3']}  ")
        lines.append(f"**Resistance levels:** R1 {pivots['r1']}, R2 {pivots['r2']}, R3 {pivots['r3']}  ")
        lines.append(f"**Pivot:** {pivots['pivot']}\n")
    if gap:
        lines.append(f"**Gap structure:** {gap['label']} ({gap['gap_pct']}% vs previous close)\n")

    lines.append("## 3. Market Sentiment Analysis")
    lines.append(f"**Classification:** {sentiment['label']}  ")
    lines.append(f"**Confidence Score:** {sentiment['confidence_pct']}%  ")
    lines.append("**Supporting reasons:**")
    if sentiment["reasons"]:
        for r in sentiment["reasons"]:
            lines.append(f"- {r}")
    else:
        lines.append("- Mixed / insufficient signal strength for a strong directional read")
    lines.append("")

    lines.append("## 4. Intraday Probability Analysis")
    lines.append("| Scenario | Probability |\n|---|---|")
    lines.append(f"| Upward Movement | {probs['up_pct']}% |")
    lines.append(f"| Downward Movement | {probs['down_pct']}% |")
    lines.append(f"| Sideways / Volatile | {probs['sideways_pct']}% |")
    lines.append("_Probabilities are a rule-based heuristic combining trend, breadth, "
                 "flows, and volatility — not a calibrated statistical forecast.\n_")

    lines.append("## 5. Price Expectation")
    if pivots and snapshot.current_price:
        lines.append(f"- Current Price: {_fmt(snapshot.current_price)}")
        lines.append(f"- Nearest Support Zone: {pivots['s1']}")
        lines.append(f"- Nearest Resistance Zone: {pivots['r1']}")
        lines.append(f"- Expected Upside Range: up to {pivots['r2']}")
        lines.append(f"- Expected Downside Range: down to {pivots['s2']}")
        lines.append(f"- Expected Trading Range: {pivots['s1']} – {pivots['r1']}\n")
    else:
        lines.append("- Insufficient data to compute pivot-based price expectation.\n")

    lines.append("## 6. ATM Option Analysis")
    if atm_strike:
        lines.append(f"Nearest ATM strike (rounded to 50): **{atm_strike}**\n")
        lines.append("| Side | Probability of Favorable Move | Confidence |")
        lines.append("|---|---|---|")
        lines.append(f"| ATM Call | {call_prob}% | {sentiment['confidence_pct']}% |")
        lines.append(f"| ATM Put | {put_prob}% | {sentiment['confidence_pct']}% |")
        stronger = "Call" if call_prob >= put_prob else "Put"
        lines.append(f"\n**Probability comparison:** {stronger} side currently shows the higher "
                     f"probability-weighted edge based on current trend/sentiment inputs. "
                     f"This is a probability comparison only — not a trade instruction.\n")
    else:
        lines.append("Current price unavailable — cannot compute ATM strike.\n")

    lines.append("## 7. Time Block Analysis")
    lines.append("| Block | Note |\n|---|---|")
    for block, note in TIME_BLOCKS:
        lines.append(f"| {block} | {note} |")
    lines.append("")

    lines.append("## 8. Risk Factors")
    lines.append("| Risk | Level |\n|---|---|")
    for risk, level in RISK_FACTORS:
        lines.append(f"| {risk} | {level} |")
    lines.append("")

    lines.append("## 9. Final Market Summary")
    lines.append(f"1. **Overall Market Bias:** {sentiment['label']}")
    lines.append(f"2. **Overall Confidence Score:** {sentiment['confidence_pct']}%")
    top_scenario = max(probs, key=probs.get)
    lines.append(f"3. **Highest Probability Scenario:** {top_scenario.replace('_pct','').title()} "
                 f"({probs[top_scenario]}%)")
    if pivots:
        lines.append(f"4. **Expected Intraday Range:** {pivots['s1']} – {pivots['r1']}")
    lines.append(f"5. **Stronger ATM Side:** {'Call' if call_prob >= put_prob else 'Put'}")
    if pivots:
        lines.append(f"6. **Key Support Level:** {pivots['s1']}")
        lines.append(f"7. **Key Resistance Level:** {pivots['r1']}")
    lines.append("8. **Major Risk Factors:** " + ", ".join([r for r, _ in RISK_FACTORS]))
    lines.append(f"9. **Expert Assessment:** Based on current data, NIFTY 50 shows a "
                 f"{sentiment['label'].lower()} bias with {sentiment['confidence_pct']}% confidence. "
                 f"The highest-probability scenario for this session is "
                 f"{top_scenario.replace('_pct','')} movement at {probs[top_scenario]}%. "
                 f"This is a probability-based, educational read of current conditions and "
                 f"should not be treated as a trading recommendation.")

    lines.append("\n---\n_This report is for educational and research purposes only. "
                 "It is not personalized financial advice and contains no buy/sell/hold "
                 "instructions. Verify all data against your broker/exchange terminal._")

    return "\n".join(lines)
