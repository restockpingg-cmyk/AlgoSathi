"""One-time-per-day interactive Upstox login helper.

Run this each trading morning before starting the runner in live mode (or before pulling
real historical data), since Upstox access tokens always expire at 3:30 AM IST:

    python -m algosathi.auth.cli_login
"""

from __future__ import annotations

from algosathi.auth.upstox_auth import exchange_code_for_token, get_login_url
from algosathi.config import get_settings


def main() -> None:
    settings = get_settings()

    if not settings.secrets.upstox_api_key or not settings.secrets.upstox_api_secret:
        print(
            "UPSTOX_API_KEY / UPSTOX_API_SECRET are not set in .env. "
            "Register an app at the Upstox Developer Console first."
        )
        return

    login_url = get_login_url(settings)
    print("1. Open this URL in your browser and log in to Upstox:\n")
    print(f"   {login_url}\n")
    print(
        "2. After login you'll be redirected to your configured redirect_uri "
        "(the page itself may show an error, that's expected). Copy the `code` "
        "query parameter from the browser's address bar.\n"
    )
    auth_code = input("Paste the code here: ").strip()

    access_token = exchange_code_for_token(settings, auth_code)
    print(f"\nLogin successful. Access token cached (valid until 3:30 AM IST tomorrow).")
    print(f"Token (first 12 chars): {access_token[:12]}...")


if __name__ == "__main__":
    main()
