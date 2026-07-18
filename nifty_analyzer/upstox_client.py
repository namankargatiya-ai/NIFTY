"""
upstox_client.py
-----------------
Thin wrapper around the Upstox API (v2/v3) for market data retrieval.
Uses real NSE-sourced data via your Upstox account -- broker-grade
LTP, true intraday candles, and live option chain, instead of the
delayed data yfinance provides.

You need:
  1. An Upstox Developer App (create one at https://upstox.com/developer/apps)
     -> gives you an API Key (client_id) and API Secret (client_secret)
  2. A daily-generated access_token (Upstox tokens expire every day,
     typically invalidated around 3:30 AM IST -- there is no long-lived
     token, so you re-authenticate once per trading day). See auth.py
     in this package for a helper to generate it.

Docs referenced (Upstox Developer API, current as of build time):
  - Full market quote:     GET /v2/market-quote/quotes
  - OHLC quotes (v3):      GET /v3/market-quote/ohlc
  - LTP quotes (v3):       GET /v3/market-quote/ltp
  - Intraday candles (v3): GET /v3/historical-candle/intraday/{key}/minutes/{n}
  - Historical candles v3: GET /v3/historical-candle/{key}/{unit}/{interval}/{to}/{from}
  - Option chain:          GET /v2/option/chain

NOTE: Upstox's API surface changes over time. If any call below starts
returning 4xx errors, check https://upstox.com/developer/api-documentation/
for the current endpoint shape before assuming this code is broken.
"""

from __future__ import annotations
import datetime as dt
from typing import Optional
from urllib.parse import quote

import pandas as pd
import requests

BASE_URL = "https://api.upstox.com"

# Common instrument keys for NSE indices
NIFTY_50_KEY = "NSE_INDEX|Nifty 50"
NIFTY_BANK_KEY = "NSE_INDEX|Nifty Bank"
INDIA_VIX_KEY = "NSE_INDEX|India VIX"


class UpstoxAPIError(RuntimeError):
    pass


class UpstoxClient:
    def __init__(self, access_token: str, timeout: int = 10):
        if not access_token:
            raise ValueError("access_token is required")
        self.access_token = access_token
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        })

    # ------------------------------------------------------------------ #
    # Low-level request helper
    # ------------------------------------------------------------------ #
    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        url = f"{BASE_URL}{path}"
        resp = self.session.get(url, params=params, timeout=self.timeout)
        try:
            payload = resp.json()
        except ValueError:
            resp.raise_for_status()
            raise UpstoxAPIError(f"Non-JSON response from {url}: {resp.text[:200]}")

        if resp.status_code >= 400 or payload.get("status") == "error":
            raise UpstoxAPIError(
                f"Upstox API error [{resp.status_code}] on {path}: {payload}"
            )
        return payload

    # ------------------------------------------------------------------ #
    # Quotes
    # ------------------------------------------------------------------ #
    def get_full_quote(self, instrument_keys: list[str]) -> dict:
        """Full market quote incl. OHLC, LTP, depth. Max 500 keys per call."""
        joined = ",".join(instrument_keys)
        payload = self._get("/v2/market-quote/quotes", {"instrument_key": joined})
        return payload.get("data", {})

    def get_ohlc_v3(self, instrument_keys: list[str], interval: str = "1d") -> dict:
        """interval: '1d' etc. Returns live_ohlc + prev_ohlc per instrument."""
        joined = ",".join(instrument_keys)
        payload = self._get("/v3/market-quote/ohlc",
                             {"instrument_key": joined, "interval": interval})
        return payload.get("data", {})

    def get_ltp_v3(self, instrument_keys: list[str]) -> dict:
        joined = ",".join(instrument_keys)
        payload = self._get("/v3/market-quote/ltp", {"instrument_key": joined})
        return payload.get("data", {})

    # ------------------------------------------------------------------ #
    # Candles
    # ------------------------------------------------------------------ #
    def get_intraday_candles(self, instrument_key: str, interval_minutes: int = 5) -> pd.DataFrame:
        """
        Current trading day's candles at the given minute interval
        (1, 3, 5, 15, 30 typically supported). Returns ascending-time
        OHLCV DataFrame with lowercase columns, or an empty DataFrame
        if no data is available (e.g. market not yet open today).
        """
        encoded_key = quote(instrument_key, safe="")
        path = f"/v3/historical-candle/intraday/{encoded_key}/minutes/{interval_minutes}"
        payload = self._get(path)
        candles = payload.get("data", {}).get("candles", [])
        return self._candles_to_df(candles)

    def get_historical_candles(self, instrument_key: str, unit: str, interval: str,
                                to_date: str, from_date: str) -> pd.DataFrame:
        """
        unit: 'minutes' | 'hours' | 'days' | 'weeks' | 'months'
        interval: e.g. '1', '30'
        to_date / from_date: 'YYYY-MM-DD' strings
        """
        encoded_key = quote(instrument_key, safe="")
        path = f"/v3/historical-candle/{encoded_key}/{unit}/{interval}/{to_date}/{from_date}"
        payload = self._get(path)
        candles = payload.get("data", {}).get("candles", [])
        return self._candles_to_df(candles)

    @staticmethod
    def _candles_to_df(candles: list) -> pd.DataFrame:
        """Upstox candle row: [timestamp, open, high, low, close, volume, oi]."""
        if not candles:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()  # API returns newest-first; flip to ascending
        return df[["open", "high", "low", "close", "volume"]]

    # ------------------------------------------------------------------ #
    # Options
    # ------------------------------------------------------------------ #
    def get_option_chain(self, instrument_key: str, expiry_date: str) -> list:
        """expiry_date: 'YYYY-MM-DD'. Returns list of strike-wise call/put data."""
        payload = self._get("/v2/option/chain",
                             {"instrument_key": instrument_key, "expiry_date": expiry_date})
        return payload.get("data", [])

    # ------------------------------------------------------------------ #
    # Convenience
    # ------------------------------------------------------------------ #
    def get_index_snapshot(self, instrument_key: str = NIFTY_50_KEY) -> dict:
        """
        Pulls current_price, previous_close, open, high, low, volume
        for an index in one call via the full quote endpoint.
        """
        data = self.get_full_quote([instrument_key])
        if not data:
            return {}
        # Response is keyed by "EXCHANGE:SYMBOL", not the instrument_key string --
        # there's exactly one entry for a single-key request, so just take it.
        entry = next(iter(data.values()))
        ohlc = entry.get("ohlc", {})
        return {
            "current_price": entry.get("last_price"),
            "open_price": ohlc.get("open"),
            "day_high": ohlc.get("high"),
            "day_low": ohlc.get("low"),
            "previous_close": entry.get("prev_close") or entry.get("close_price"),
            "volume": entry.get("volume"),
        }
