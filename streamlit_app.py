"""
streamlit_app.py
-----------------
Web UI for the NIFTY 50 market analyzer, built for Streamlit Cloud.

This is the file to point Streamlit Cloud's "Main file path" at --
NOT main.py (that's a separate command-line script for local/terminal
use and will not run correctly as a Streamlit app).

Deployment checklist (Streamlit Cloud):
  1. Repo root must contain: streamlit_app.py, requirements.txt,
     and the nifty_analyzer/ package folder (with its __init__.py).
  2. In the Streamlit Cloud app settings, "Main file path" = streamlit_app.py
  3. requirements.txt must include `streamlit` (see this project's
     requirements.txt).
  4. If using Upstox, add UPSTOX_ACCESS_TOKEN as a Secret in the app's
     "Settings -> Secrets" panel instead of pasting it in the UI, if
     you want it pre-filled. Otherwise paste it in the sidebar each day.
"""

import datetime as dt
import sys
import traceback

import streamlit as st

# --- Make sure the nifty_analyzer package is importable -------------------
# On Streamlit Cloud the working directory is the repo root, so this import
# works as long as the nifty_analyzer/ folder was actually pushed to GitHub
# alongside this file. If you see ModuleNotFoundError here, that's almost
# always the cause -- check your repo contents on GitHub directly.
try:
    from nifty_analyzer.fetch_data import build_snapshot, build_snapshot_from_upstox, NIFTY_TICKER
    from nifty_analyzer.report import generate_report
except ModuleNotFoundError as e:
    st.error(
        "Could not import the `nifty_analyzer` package.\n\n"
        f"**{e}**\n\n"
        "This almost always means the `nifty_analyzer/` folder (with its "
        "`__init__.py`) wasn't pushed to your GitHub repo, or isn't sitting "
        "next to `streamlit_app.py` at the repo root. Check your repo's "
        "file listing on GitHub to confirm both are present."
    )
    st.code(traceback.format_exc())
    st.stop()


st.set_page_config(page_title="NIFTY 50 Market Analyzer", page_icon="📈", layout="wide")

st.title("📈 NIFTY 50 Market Analyzer")
st.caption(
    "Educational, probability-based market research report. "
    "Not financial advice — no buy/sell/hold signals."
)

# ---------------------------------------------------------------------- #
# Sidebar: data source configuration
# ---------------------------------------------------------------------- #
with st.sidebar:
    st.header("Data Source")
    source = st.radio(
        "Choose data source",
        options=["yfinance (delayed, no login needed)", "Upstox (live, needs daily token)"],
        index=0,
    )

    upstox_token = None
    index_key = None
    if source.startswith("Upstox"):
        st.markdown(
            "Upstox access tokens expire daily (~3:30 AM IST). "
            "Generate today's token locally with:\n\n"
            "```\npython -m nifty_analyzer.auth login\npython -m nifty_analyzer.auth token --code XXXX\n```"
        )
        # Prefer a Streamlit Secret if you've set one, otherwise let the
        # user paste today's token directly (it's never written to disk here).
        default_token = st.secrets.get("UPSTOX_ACCESS_TOKEN", "") if hasattr(st, "secrets") else ""
        upstox_token = st.text_input("Upstox access token", value=default_token, type="password")
        index_key = st.text_input("Instrument key", value="NSE_INDEX|Nifty 50")

    st.divider()
    st.header("Session Context (optional)")
    st.caption("Free data sources don't reliably expose these — paste today's published figures if you have them.")
    col1, col2 = st.columns(2)
    with col1:
        advances = st.number_input("Advances", min_value=0, value=0, step=1)
        fii = st.number_input("FII net (₹ Cr)", value=0.0, step=10.0)
    with col2:
        declines = st.number_input("Declines", min_value=0, value=0, step=1)
        dii = st.number_input("DII net (₹ Cr)", value=0.0, step=10.0)
    vix_change = st.number_input("India VIX % change vs prev session", value=0.0, step=0.5)

    run_button = st.button("🔄 Generate Report", type="primary", use_container_width=True)


# ---------------------------------------------------------------------- #
# Main panel
# ---------------------------------------------------------------------- #
today = dt.datetime.now()
is_weekday = today.weekday() < 5
status_col1, status_col2 = st.columns([3, 1])
with status_col1:
    st.write(f"**Current time:** {today.strftime('%Y-%m-%d %H:%M:%S')} IST")
with status_col2:
    if is_weekday:
        st.success("Weekday")
    else:
        st.warning("Weekend")

if not is_weekday:
    st.info(
        "NSE doesn't trade on weekends. Figures below (if you generate a report) "
        "will reflect the most recently completed session, not a live tape."
    )

if run_button:
    with st.spinner(f"Fetching NIFTY 50 data via {'Upstox' if source.startswith('Upstox') else 'yfinance'}..."):
        try:
            if source.startswith("Upstox"):
                if not upstox_token:
                    st.error("Please paste today's Upstox access token in the sidebar first.")
                    st.stop()
                snapshot = build_snapshot_from_upstox(upstox_token, index_key=index_key or None)
            else:
                snapshot = build_snapshot(NIFTY_TICKER)
        except Exception as e:
            st.error(f"Data fetch failed: {e}")
            st.code(traceback.format_exc())
            st.stop()

    report_md = generate_report(
        snapshot,
        advances=advances or None,
        declines=declines or None,
        fii_net_cr=fii or None,
        dii_net_cr=dii or None,
        vix_change_pct=vix_change or None,
    )

    st.session_state["last_report"] = report_md
    st.session_state["last_generated_at"] = today

if "last_report" in st.session_state:
    st.caption(f"Report generated at {st.session_state['last_generated_at'].strftime('%Y-%m-%d %H:%M:%S')} IST")
    st.markdown(st.session_state["last_report"])
    st.download_button(
        "⬇️ Download report as Markdown",
        data=st.session_state["last_report"],
        file_name=f"nifty_report_{today.strftime('%Y%m%d_%H%M')}.md",
        mime="text/markdown",
    )
else:
    st.info("Configure your data source in the sidebar, then click **Generate Report**.")

st.divider()
st.caption(
    "⚠️ Educational and research purposes only. Not personalized financial advice. "
    "Contains no buy/sell/hold instructions. Verify all data against your broker/exchange terminal."
)
