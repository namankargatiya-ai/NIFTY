"""
fetch_data.py
-------------
Handles all live/near-live data retrieval for NIFTY 50.

Data sources:
- yfinance          -> spot OHLC, intraday candles, historical daily bars, India VIX
- nsepython (opt.)  -> live option chain (for ATM call/put OI & IV), market breadth

All functions fail soft: if a source is unreachable or a library is
missing, they return None / empty structures rather than raising, so
the rest of the pipeline can degrade gracefully instead of crashing.
"""

from __future__ import annotations
import datetime as dt  # noqa: F401 (used in build_snapshot_from_upstox)
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None

try:
    from nsepython import nse_optionchain_scrapper  # type: ignore
except Exception:  # pragma: no cover
    nse_optionchain_scrapper = None


NIFTY_TICKER = "^NSEI"
VIX_TICKER = "^INDIAVIX"


@dataclass
class MarketSnapshot:
    """Container for a single point-in-time market data pull."""
    symbol: str = "NIFTY 50"
    fetched_at: dt.datetime = field(default_factory=dt.datetime.now)

    current_price: Optional[float] = None
    previous_close: Optional[float] = None
    open_price: Optional[float] = None
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    volume: Optional[float] = None
    vwap: Optional[float] = None
    india_vix: Optional[float] = None

    intraday_5m: Optional[pd.DataFrame] = None
    intraday_15m: Optional[pd.DataFrame] = None
    intraday_30m: Optional[pd.DataFrame] = None
    daily_history: Optional[pd.DataFrame] = None

    option_chain: Optional[dict] = None

    def is_market_open_today(self) -> bool:
        """NSE trades Mon-Fri only (holiday calendar not checked here)."""
        return self.fetched_at.weekday() < 5


def _safe_download(ticker: str, **kwargs) -> Optional[pd.DataFrame]:
    if yf is None:
        return None
    try:
        df = yf.download(ticker, progress=False, **kwargs)
        if df is None or df.empty:
            return None
        return df
    except Exception:
        return None


def fetch_spot_and_ohlc(ticker: str = NIFTY_TICKER) -> dict:
    """Fetch previous close, open, day high/low, and current/last price."""
    info = {}
    try:
        t = yf.Ticker(ticker)
        fast = t.fast_info
        info["current_price"] = float(fast.get("lastPrice") or fast.get("last_price"))
        info["previous_close"] = float(fast.get("previousClose") or fast.get("regularMarketPreviousClose"))
        info["open_price"] = float(fast.get("open") or fast.get("regularMarketOpen") or 0) or None
        info["day_high"] = float(fast.get("dayHigh") or fast.get("regularMarketDayHigh") or 0) or None
        info["day_low"] = float(fast.get("dayLow") or fast.get("regularMarketDayLow") or 0) or None
        info["volume"] = float(fast.get("lastVolume") or fast.get("regularMarketVolume") or 0) or None
    except Exception:
        pass
    return info


def fetch_intraday(ticker: str = NIFTY_TICKER, interval: str = "5m", period: str = "5d") -> Optional[pd.DataFrame]:
    """Fetch intraday candles. interval: '5m' | '15m' | '30m'."""
    df = _safe_download(ticker, period=period, interval=interval)
    if df is not None and not df.empty:
        df = df.rename(columns=str.lower)
    return df


def fetch_daily_history(ticker: str = NIFTY_TICKER, period: str = "6mo") -> Optional[pd.DataFrame]:
    """Fetch daily OHLCV history, used for EMA/RSI/SMA calculations."""
    df = _safe_download(ticker, period=period, interval="1d")
    if df is not None and not df.empty:
        df = df.rename(columns=str.lower)
    return df


def fetch_india_vix() -> Optional[float]:
    try:
        t = yf.Ticker(VIX_TICKER)
        fast = t.fast_info
        val = fast.get("lastPrice") or fast.get("last_price")
        return float(val) if val else None
    except Exception:
        return None


def fetch_option_chain(symbol: str = "NIFTY") -> Optional[dict]:
    """
    Fetch live NSE option chain via nsepython (best-effort).
    Returns raw dict from NSE's API, or None if unavailable
    (NSE frequently rate-limits / blocks non-browser requests).
    """
    if nse_optionchain_scrapper is None:
        return None
    try:
        return nse_optionchain_scrapper(symbol)
    except Exception:
        return None


def compute_intraday_vwap(intraday_df: pd.DataFrame) -> Optional[float]:
    """
    VWAP = cumulative(typical_price * volume) / cumulative(volume)
    for the current session's intraday bars.
    """
    if intraday_df is None or intraday_df.empty:
        return None
    df = intraday_df.copy()
    required = {"high", "low", "close", "volume"}
    if not required.issubset(set(df.columns)):
        return None
    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    cum_vol = df["volume"].cumsum()
    cum_tp_vol = (typical_price * df["volume"]).cumsum()
    if cum_vol.iloc[-1] == 0:
        return None
    return float(cum_tp_vol.iloc[-1] / cum_vol.iloc[-1])


def build_snapshot(ticker: str = NIFTY_TICKER) -> MarketSnapshot:
    """High-level convenience function: pulls everything needed for the report (yfinance)."""
    snap = MarketSnapshot()

    spot = fetch_spot_and_ohlc(ticker)
    snap.current_price = spot.get("current_price")
    snap.previous_close = spot.get("previous_close")
    snap.open_price = spot.get("open_price")
    snap.day_high = spot.get("day_high")
    snap.day_low = spot.get("day_low")
    snap.volume = spot.get("volume")

    snap.intraday_5m = fetch_intraday(ticker, interval="5m", period="5d")
    snap.intraday_15m = fetch_intraday(ticker, interval="15m", period="1mo")
    snap.intraday_30m = fetch_intraday(ticker, interval="30m", period="1mo")
    snap.daily_history = fetch_daily_history(ticker, period="6mo")

    if snap.intraday_5m is not None:
        snap.vwap = compute_intraday_vwap(snap.intraday_5m)

    snap.india_vix = fetch_india_vix()
    snap.option_chain = fetch_option_chain("NIFTY")

    return snap


def build_snapshot_from_upstox(access_token: str,
                                index_key: Optional[str] = None,
                                vix_key: Optional[str] = None) -> MarketSnapshot:
    """
    Broker-grade alternative to build_snapshot(): pulls real NSE data
    through your Upstox account (LTP, true OHLC, intraday candles at
    1/5/15/30-min, India VIX, and daily history) instead of yfinance's
    delayed feed.

    Requires a same-day Upstox access_token -- see nifty_analyzer/auth.py
    to generate one.
    """
    from .upstox_client import UpstoxClient, NIFTY_50_KEY, INDIA_VIX_KEY

    index_key = index_key or NIFTY_50_KEY
    vix_key = vix_key or INDIA_VIX_KEY

    client = UpstoxClient(access_token)
    snap = MarketSnapshot(symbol=index_key)

    spot = client.get_index_snapshot(index_key)
    snap.current_price = spot.get("current_price")
    snap.previous_close = spot.get("previous_close")
    snap.open_price = spot.get("open_price")
    snap.day_high = spot.get("day_high")
    snap.day_low = spot.get("day_low")
    snap.volume = spot.get("volume")

    # Intraday candles at each timeframe, current trading day only.
    try:
        snap.intraday_5m = client.get_intraday_candles(index_key, interval_minutes=5)
    except Exception:
        snap.intraday_5m = None
    try:
        snap.intraday_15m = client.get_intraday_candles(index_key, interval_minutes=15)
    except Exception:
        snap.intraday_15m = None
    try:
        snap.intraday_30m = client.get_intraday_candles(index_key, interval_minutes=30)
    except Exception:
        snap.intraday_30m = None

    # Daily history (past 6 months) for SMA/EMA/RSI trend confirmation.
    try:
        today = dt.date.today()
        six_months_ago = today - dt.timedelta(days=182)
        snap.daily_history = client.get_historical_candles(
            index_key, unit="days", interval="1",
            to_date=today.isoformat(), from_date=six_months_ago.isoformat(),
        )
    except Exception:
        snap.daily_history = None

    # Real VWAP computed from 1-minute intraday candles (more accurate
    # than deriving it from 5-min bars).
    try:
        one_min = client.get_intraday_candles(index_key, interval_minutes=1)
        snap.vwap = compute_intraday_vwap(one_min)
    except Exception:
        if snap.intraday_5m is not None:
            snap.vwap = compute_intraday_vwap(snap.intraday_5m)

    # India VIX
    try:
        vix_spot = client.get_index_snapshot(vix_key)
        snap.india_vix = vix_spot.get("current_price")
    except Exception:
        snap.india_vix = None

    # Option chain left to the caller (needs an expiry_date) -- see
    # UpstoxClient.get_option_chain(index_key, expiry_date).
    snap.option_chain = None

    return snap
