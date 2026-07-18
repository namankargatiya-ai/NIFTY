# NIFTY 50 Market Analyzer

A lightweight, educational Python toolkit that pulls NIFTY 50 market data,
computes standard technical indicators (EMA, RSI, MACD, pivot support/resistance,
VWAP), and generates a structured, probability-based market research report —
in the same format used by professional pre-market/intraday research notes.

> ⚠️ **Disclaimer:** This project is for **educational and research purposes
> only**. It is not financial advice, does not issue buy/sell/hold
> instructions, and the probability estimates are simple rule-based
> heuristics — not a statistically validated predictive model. Always verify
> data against your broker/exchange terminal.

## Features

- Live spot price, OHLC, volume, and India VIX via `yfinance`
- Intraday 5-min / 15-min / 30-min trend + EMA20/EMA50 + RSI(14) + MACD
- Classic floor-trader pivot support/resistance levels
- Gap-up / gap-down structure detection
- Rule-based sentiment scoring (Bullish → Bearish, 5-point scale) with
  transparent, listed reasons
- Up / Down / Sideways probability estimation (always sums to 100%)
- ATM call/put probability comparison (probability only — no trade signals)
- Optional live NSE option chain fetch via `nsepython` (best-effort — NSE
  often rate-limits non-browser requests)
- Full markdown report generation, matching a professional research template

## Project Structure

```
nifty-analyzer/
├── main.py                     # CLI entry point
├── requirements.txt
├── nifty_analyzer/
│   ├── __init__.py
│   ├── fetch_data.py           # live data retrieval (yfinance, nsepython)
│   ├── indicators.py           # EMA, RSI, MACD, pivots, trend classification
│   ├── sentiment.py            # sentiment scoring + probability estimation
│   └── report.py               # assembles everything into the final report
├── tests/
│   └── test_offline.py         # runs the full pipeline on synthetic data
│                                # (no network needed — good for CI)
└── .github/workflows/ci.yml    # GitHub Actions: runs tests on every push
```

## Installation

```bash
git clone https://github.com/<your-username>/nifty-analyzer.git
cd nifty-analyzer
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

```bash
# Basic: fetch live data and print the report
python main.py

# Save the report to a file
python main.py --save report.md

# Supply market breadth / institutional flow data manually
# (free APIs don't always expose these reliably)
python main.py --breadth 2012 2224 --fii -376.41 --dii 1017.89 --vix-change -2.92

# Use a different ticker (e.g. Bank Nifty)
python main.py --ticker "^NSEBANK"
```

## Deploying as a Web App (Streamlit Cloud)

There are **two different entry points** in this project — using the wrong
one is the most common source of errors:

| File | Purpose | How to run it |
|---|---|---|
| `main.py` | Command-line script | `python main.py` in a terminal |
| `streamlit_app.py` | Web app (sidebar, buttons, live report) | Streamlit Cloud, or `streamlit run streamlit_app.py` locally |

**If you saw `ModuleNotFoundError` on Streamlit Cloud pointing at `main.py`:**
that's expected — `main.py` uses `argparse` and isn't built to run as a
Streamlit page. Point Streamlit Cloud at **`streamlit_app.py`** instead.

### Steps to deploy

1. Push this whole repo (including the `nifty_analyzer/` folder) to GitHub.
   Double-check on github.com that `nifty_analyzer/__init__.py` and its
   sibling files actually show up in the repo — a `ModuleNotFoundError` for
   `nifty_analyzer` almost always means that folder didn't get pushed.
2. On [share.streamlit.io](https://share.streamlit.io), create a new app
   pointing at your repo.
3. Set **"Main file path"** to `streamlit_app.py` (not `main.py`).
4. Confirm `requirements.txt` is at the **repo root** — Streamlit Cloud
   installs from that file automatically.
5. (Optional) If you want your Upstox token pre-filled instead of pasting
   it into the UI each day, add it under your app's **Settings → Secrets**:
   ```toml
   UPSTOX_ACCESS_TOKEN = "your_daily_token"
   ```

### Running it locally instead

```bash
streamlit run streamlit_app.py
```

## Is the Data "Live"?

- **yfinance (default):** near-real-time but **exchange-delayed** — fine for
  technical/educational analysis, not for latency-sensitive decisions.
- **Upstox (with your access token):** genuine **real-time NSE data** during
  market hours (LTP, true intraday candles, live VWAP), since it flows
  through your actual broker market-data entitlement.

## Running Without Live Market Access

If you don't have network access to Yahoo Finance / NSE (e.g. in a sandboxed
CI environment), you can validate the whole pipeline with synthetic data:

```bash
python -m tests.test_offline
```

This exercises indicator calculation, sentiment scoring, and full report
generation end-to-end without hitting any external API.

## Using Upstox for Live Broker-Grade Data

By default this tool uses `yfinance`, which mirrors NSE data with a short
delay. If you have an **Upstox account**, you can plug in your API token
instead, which gets you:

- Real NSE-sourced LTP and true intraday OHLC candles (1/5/15/30-min),
  not yfinance's delayed feed
- A genuine intraday VWAP computed from real 1-minute candles
- Live India VIX
- A foundation to add live option-chain OI/IV data (`UpstoxClient.get_option_chain`)

### 1. Create an Upstox Developer App

Go to [Upstox Developer Apps](https://upstox.com/developer/apps), create an
app, and note your **API Key** (`client_id`) and **API Secret**
(`client_secret`). Set a redirect URI you control (even `http://localhost`
works for personal use).

### 2. Generate a daily access token

⚠️ **Upstox access tokens expire every day** (around 3:30 AM IST) — there's
no long-lived refresh token on the standard plan, so this is a once-per-
trading-day step, not a one-time setup.

```bash
export UPSTOX_API_KEY="your_client_id"
export UPSTOX_API_SECRET="your_client_secret"
export UPSTOX_REDIRECT_URI="http://localhost"

# Step 1: get the login URL, open it in a browser, log in, approve the app
python -m nifty_analyzer.auth login

# Step 2: after approving, Upstox redirects you to
#   http://localhost/?code=XXXXXX&state=nifty_analyzer
# Copy the `code` value from that URL, then:
python -m nifty_analyzer.auth token --code XXXXXX

# This prints your access_token and an export command. Run it:
export UPSTOX_ACCESS_TOKEN="eyJ0eXAi..."
```

### 3. Run the analyzer against Upstox data

```bash
# Auto-detected: if UPSTOX_ACCESS_TOKEN is set, Upstox is used automatically
python main.py

# Or explicitly:
python main.py --source upstox --upstox-token "$UPSTOX_ACCESS_TOKEN"

# Bank Nifty instead of Nifty 50:
python main.py --source upstox --index-key "NSE_INDEX|Nifty Bank"
```

If you want to automate the daily token refresh (skip the interactive
browser step), some third-party libraries like `upstox-totp` can drive the
login via TOTP — see their docs. That's outside the scope of this project
since it involves handling your login credentials directly.

### Notes on Upstox data quality

- Intraday candle endpoints have occasionally shown brief gaps or short
  delays (a few seconds) during high-load periods, per Upstox's own
  community forum — treat intraday data as near-real-time, not
  zero-latency tick data.
- The option-chain integration (`UpstoxClient.get_option_chain`) is wired
  up but not yet plugged into the report — it needs an `expiry_date`
  argument. Feel free to extend `report.py` to pull ATM call/put OI and
  IV directly from it instead of the heuristic probability estimate.

## Data Sources & Limitations

- **yfinance** pulls from Yahoo Finance, which mirrors NSE data with a short
  delay — not tick-level real-time. Good enough for educational/technical
  analysis, not for latency-sensitive use.
- **India VIX** (`^INDIAVIX`) and intraday candles depend on Yahoo Finance
  coverage, which can occasionally be sparse for Indian indices.
- **nsepython** scrapes NSE's public option-chain endpoint. NSE frequently
  rate-limits or blocks non-browser traffic, so option-chain fetches are
  best-effort and fail gracefully (`None`) if blocked.
- **Market breadth (advance/decline) and FII/DII flow** aren't reliably
  available from free APIs — pass them manually via `--breadth`, `--fii`,
  `--dii` using figures published by NSE/exchanges after each session.
- The script checks `datetime.weekday()` to flag non-trading days but does
  **not** account for NSE holidays — cross-check the exchange holiday
  calendar for those dates.

## Publishing This to Your Own GitHub Repository

```bash
cd nifty-analyzer
git init
git add .
git commit -m "Initial commit: NIFTY 50 market analyzer"
git branch -M main
git remote add origin https://github.com/<your-username>/nifty-analyzer.git
git push -u origin main
```

(Create the empty repo on GitHub first via github.com/new, or via
`gh repo create nifty-analyzer --public --source=. --push` if you have the
GitHub CLI installed and authenticated.)

## License

MIT — see `LICENSE`.
