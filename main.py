#!/usr/bin/env python3
"""
main.py
-------
Entry point: fetches live NIFTY 50 data, runs the technical/sentiment
pipeline, and prints (or saves) the full markdown research report.

Usage:
    python main.py                     # print report to stdout
    python main.py --save report.md    # also save to file
    python main.py --breadth 1500 1200 --fii -376.41 --dii 1017.89
                                        # supply market-breadth / flow
                                        # data manually (NSE doesn't
                                        # always expose these via free
                                        # APIs, so you can paste today's
                                        # published figures)

Requires: pip install -r requirements.txt
"""

import argparse
import os
import sys

from nifty_analyzer.fetch_data import build_snapshot, build_snapshot_from_upstox, NIFTY_TICKER
from nifty_analyzer.report import generate_report


def main():
    parser = argparse.ArgumentParser(description="NIFTY 50 market research report generator")
    parser.add_argument("--source", choices=["yfinance", "upstox"], default=None,
                         help="Data source. Defaults to 'upstox' if UPSTOX_ACCESS_TOKEN is set, "
                              "else 'yfinance'.")
    parser.add_argument("--ticker", default=NIFTY_TICKER, help="Yahoo Finance ticker (default ^NSEI)")
    parser.add_argument("--upstox-token", default=os.environ.get("UPSTOX_ACCESS_TOKEN"),
                         help="Upstox access token (or set UPSTOX_ACCESS_TOKEN env var). "
                              "Generate one with `python -m nifty_analyzer.auth login/token` -- "
                              "see README. Expires daily (~3:30 AM IST).")
    parser.add_argument("--index-key", default=None,
                         help="Upstox instrument key for the index (default NSE_INDEX|Nifty 50)")
    parser.add_argument("--save", metavar="FILE", help="Save report to this markdown file")
    parser.add_argument("--breadth", nargs=2, type=int, metavar=("ADVANCES", "DECLINES"),
                         help="Manually supply advance/decline counts")
    parser.add_argument("--fii", type=float, help="FII net cash flow in ₹ crore (negative = selling)")
    parser.add_argument("--dii", type=float, help="DII net cash flow in ₹ crore (negative = selling)")
    parser.add_argument("--vix-change", type=float, help="India VIX %% change vs previous session")
    args = parser.parse_args()

    source = args.source or ("upstox" if args.upstox_token else "yfinance")

    if source == "upstox":
        if not args.upstox_token:
            print("ERROR: --source upstox requires --upstox-token or UPSTOX_ACCESS_TOKEN env var.\n"
                  "See README.md 'Using Upstox for Live Broker Data' for how to generate one.",
                  file=sys.stderr)
            sys.exit(1)
        print("Fetching live NIFTY 50 data via Upstox...", file=sys.stderr)
        snapshot = build_snapshot_from_upstox(args.upstox_token, index_key=args.index_key)
    else:
        print("Fetching NIFTY 50 data via yfinance...", file=sys.stderr)
        snapshot = build_snapshot(args.ticker)

    advances, declines = (args.breadth if args.breadth else (None, None))

    report_md = generate_report(
        snapshot,
        advances=advances,
        declines=declines,
        fii_net_cr=args.fii,
        dii_net_cr=args.dii,
        vix_change_pct=args.vix_change,
    )

    print(report_md)

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            f.write(report_md)
        print(f"\nSaved report to {args.save}", file=sys.stderr)


if __name__ == "__main__":
    main()
