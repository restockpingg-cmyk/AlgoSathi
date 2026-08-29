from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from pathlib import Path
from urllib.parse import urlencode

import requests

from algosathi.config import Settings

AUTHORIZE_URL = "https://api.upstox.com/v2/login/authorization/dialog"
TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
TOKEN_CACHE_PATH = DATA_DIR / "token_cache.json"

# Upstox access tokens always expire at 3:30 AM IST, regardless of when they were issued.
TOKEN_EXPIRY_TIME = time(3, 30)


class AuthRequiredError(RuntimeError):
    pass


def get_login_url(settings: Settings) -> str:
    params = {
        "client_id": settings.secrets.upstox_api_key,
        "redirect_uri": settings.secrets.upstox_redirect_uri,
        "response_type": "code",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_token(settings: Settings, auth_code: str) -> str:
    response = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        data={
            "code": auth_code,
            "client_id": settings.secrets.upstox_api_key,
            "client_secret": settings.secrets.upstox_api_secret,
            "redirect_uri": settings.secrets.upstox_redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=15,
    )
    response.raise_for_status()
    access_token = response.json()["access_token"]
    save_token(access_token)
    return access_token


def _next_expiry(issued_at: datetime) -> datetime:
    expiry_today = datetime.combine(issued_at.date(), TOKEN_EXPIRY_TIME)
    if issued_at.time() < TOKEN_EXPIRY_TIME:
        return expiry_today
    return expiry_today + timedelta(days=1)


def save_token(access_token: str) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    issued_at = datetime.now()
    payload = {
        "access_token": access_token,
        "issued_at": issued_at.isoformat(),
        "expires_at": _next_expiry(issued_at).isoformat(),
    }
    TOKEN_CACHE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def get_valid_token(settings: Settings) -> str:
    if not TOKEN_CACHE_PATH.exists():
        raise AuthRequiredError(
            "No Upstox access token cached. Run `python -m algosathi.auth.cli_login` first."
        )
    payload = json.loads(TOKEN_CACHE_PATH.read_text(encoding="utf-8"))
    expires_at = datetime.fromisoformat(payload["expires_at"])
    if datetime.now() >= expires_at:
        raise AuthRequiredError(
            f"Cached Upstox access token expired at {expires_at.isoformat()}. "
            "Run `python -m algosathi.auth.cli_login` again."
        )
    return payload["access_token"]
