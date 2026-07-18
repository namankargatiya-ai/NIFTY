"""
auth.py
-------
Helper for Upstox's OAuth 2.0 authorization-code flow.

Upstox access tokens are valid for a single trading day (they expire
around 3:30 AM IST) -- there is no long-lived refresh token on the
standard plan, so you need to regenerate the token once per day.

This module doesn't automate clicking "Allow" on Upstox's login page
(that's an interactive, human step by design, for account security).
It automates everything else: building the login URL, and exchanging
the authorization code for an access token.

Typical flow:
    1. Run `python -m nifty_analyzer.auth login` -- prints a URL.
    2. Open that URL, log into Upstox, approve the app.
    3. Upstox redirects to your redirect_uri with `?code=...` in the
       query string. Copy that code.
    4. Run `python -m nifty_analyzer.auth token --code <CODE>` -- prints
       your access_token. Export it as UPSTOX_ACCESS_TOKEN.
"""

from __future__ import annotations
import argparse
import os
import sys
from urllib.parse import urlencode

import requests

AUTH_DIALOG_URL = "https://api.upstox.com/v2/login/authorization/dialog"
TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"


def build_login_url(client_id: str, redirect_uri: str, state: str = "nifty_analyzer") -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{AUTH_DIALOG_URL}?{urlencode(params)}"


def exchange_code_for_token(client_id: str, client_secret: str,
                             redirect_uri: str, code: str) -> dict:
    """
    Exchanges a single-use authorization code for an access token.
    Returns the full JSON response (includes access_token, user_name,
    email, exchanges enabled, etc.).
    """
    data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    resp = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=data,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def _cli():
    parser = argparse.ArgumentParser(description="Upstox OAuth helper")
    sub = parser.add_subparsers(dest="command", required=True)

    login_p = sub.add_parser("login", help="Print the Upstox login URL to open in a browser")
    login_p.add_argument("--client-id", default=os.environ.get("UPSTOX_API_KEY"))
    login_p.add_argument("--redirect-uri", default=os.environ.get("UPSTOX_REDIRECT_URI"))

    token_p = sub.add_parser("token", help="Exchange an authorization code for an access token")
    token_p.add_argument("--code", required=True, help="The `code` query param from your redirect URL")
    token_p.add_argument("--client-id", default=os.environ.get("UPSTOX_API_KEY"))
    token_p.add_argument("--client-secret", default=os.environ.get("UPSTOX_API_SECRET"))
    token_p.add_argument("--redirect-uri", default=os.environ.get("UPSTOX_REDIRECT_URI"))

    args = parser.parse_args()

    if args.command == "login":
        if not args.client_id or not args.redirect_uri:
            print("ERROR: need --client-id and --redirect-uri "
                  "(or UPSTOX_API_KEY / UPSTOX_REDIRECT_URI env vars)", file=sys.stderr)
            sys.exit(1)
        print(build_login_url(args.client_id, args.redirect_uri))

    elif args.command == "token":
        if not all([args.client_id, args.client_secret, args.redirect_uri]):
            print("ERROR: need --client-id, --client-secret, --redirect-uri "
                  "(or UPSTOX_API_KEY / UPSTOX_API_SECRET / UPSTOX_REDIRECT_URI env vars)",
                  file=sys.stderr)
            sys.exit(1)
        result = exchange_code_for_token(args.client_id, args.client_secret,
                                          args.redirect_uri, args.code)
        access_token = result.get("access_token")
        if access_token:
            print(f"\nAccess token (valid until ~3:30 AM IST tomorrow):\n{access_token}\n")
            print("Set it for this session with:")
            print(f"  export UPSTOX_ACCESS_TOKEN='{access_token}'")
        else:
            print("No access_token in response:", result, file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    _cli()
