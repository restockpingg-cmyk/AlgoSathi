"""Reads candles back out of Supabase, so a local backtest can run against the same history
the web backtester sees (written there by scripts/sync_candles.py)."""

from __future__ import annotations

import pandas as pd

from algosathi.config import Settings
from algosathi.persistence.supabase_client import get_client

# Supabase caps a single select at 1000 rows, so walk the range in pages.
_PAGE_SIZE = 1000


def fetch_candles(symbol: str, timeframe_minutes: int, settings: Settings) -> pd.DataFrame:
    client = get_client(settings)
    if client is None:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY are not set in .env")

    rows: list[dict] = []
    offset = 0
    while True:
        try:
            page = (
                client.table("candles")
                .select("timestamp,open,high,low,close,volume")
                .eq("symbol", symbol)
                .eq("timeframe_minutes", timeframe_minutes)
                .order("timestamp")
                .range(offset, offset + _PAGE_SIZE - 1)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001 — surface a readable cause, whatever it is
            # A free-tier project that has been paused answers with a Cloudflare 521 page,
            # which postgrest re-raises as an unreadable wall of HTML. Say what it means.
            raise RuntimeError(
                f"Could not read candles from Supabase: {type(exc).__name__}. "
                "If the project has been paused for inactivity, restore it from the "
                "Supabase dashboard and wait a couple of minutes for it to come up."
            ) from exc
        rows.extend(page.data)
        if len(page.data) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    if not rows:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    candles = pd.DataFrame(rows)
    candles["timestamp"] = pd.to_datetime(candles["timestamp"])
    return candles.sort_values("timestamp").reset_index(drop=True)
