"""Pulls historical candles from Upstox and upserts them into Supabase's `candles` table, so
the web backtester (which has no Upstox access of its own) has data to run against.

Run locally, after a daily Upstox login (see README's "Going live" section):

    .venv\\Scripts\\python scripts\\sync_candles.py --symbol INFY --interval 5 --lookback-days 28

Requires SUPABASE_URL / SUPABASE_SERVICE_KEY in .env. Upstox's v3 historical-candle API caps
the date range per request depending on interval: ~1 month for 1-15 minute candles, ~1 quarter
for 16-300 minute or 1-5 hour candles, no limit for daily/weekly/monthly. Run this repeatedly
(e.g. daily via cron) to build up a longer history for backtesting.
"""

from __future__ import annotations

import argparse
from datetime import date

from algosathi.auth.upstox_auth import get_valid_token
from algosathi.config import get_settings
from algosathi.market_data.upstox_historical import UpstoxHistoricalProvider
from algosathi.persistence.supabase_client import get_client


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Upstox candles into Supabase")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--exchange", default="NSE_EQ")
    parser.add_argument("--interval", type=int, default=5, help="candle interval in minutes")
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=28,
        help="stay under Upstox's per-request cap (~1 month for 1-15min candles)",
    )
    parser.add_argument(
        "--to-date",
        type=str,
        default=None,
        help="ISO date (YYYY-MM-DD) to end the window at; defaults to today. Use this to "
        "walk further back than one request's cap allows, e.g. --to-date <oldest synced date> "
        "to fetch the preceding window.",
    )
    args = parser.parse_args()

    settings = get_settings()
    client = get_client(settings)
    if client is None:
        raise SystemExit("SUPABASE_URL / SUPABASE_SERVICE_KEY are not set in .env")

    to_date = date.fromisoformat(args.to_date) if args.to_date else None
    token = get_valid_token(settings)
    provider = UpstoxHistoricalProvider(access_token=token, lookback_days=args.lookback_days)
    candles = provider.get_recent_candles(
        symbol=args.symbol, exchange=args.exchange, interval_minutes=args.interval, to_date=to_date
    )

    rows = [
        {
            "symbol": args.symbol,
            "timeframe_minutes": args.interval,
            "timestamp": row.timestamp.isoformat(),
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
            "volume": int(row.volume),
        }
        for row in candles.itertuples()
    ]

    if not rows:
        print("No candles returned; nothing to sync.")
        return

    client.table("candles").upsert(rows, on_conflict="symbol,timeframe_minutes,timestamp").execute()
    print(f"Synced {len(rows)} candles for {args.symbol} ({args.interval}m) to Supabase.")


if __name__ == "__main__":
    main()
