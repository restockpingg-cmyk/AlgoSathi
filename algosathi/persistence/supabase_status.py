"""Live-run telemetry and the kill switch.

Everything here is best-effort in the same spirit as supabase_sync.push_fill: a dashboard
that cannot be reached must never stop the bot from trading, and must never crash it. The one
exception is the kill switch, which fails *safe* — if we cannot read the flag we assume
trading is still permitted only because the caller passes a default, see is_trading_enabled.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger

from algosathi.config import Settings
from algosathi.core.models import Signal
from algosathi.persistence.supabase_client import get_client


def push_status(settings: Settings, symbol: str, **fields: Any) -> None:
    """Upserts one symbol's bot_status row. Extra keys are passed straight through, so the
    caller decides what is worth reporting on any given loop."""
    client = get_client(settings)
    if client is None:
        return
    row = {
        "symbol": symbol,
        "updated_at": datetime.now().astimezone().isoformat(),
        **fields,
    }
    try:
        client.table("bot_status").upsert(row, on_conflict="symbol").execute()
    except Exception as exc:  # noqa: BLE001 — telemetry must never take the bot down
        logger.warning(f"Could not push bot status: {exc}")


def push_signal(settings: Settings, signal: Signal, price: float | None, acted: bool) -> None:
    client = get_client(settings)
    if client is None:
        return
    try:
        client.table("signals").insert(
            {
                "symbol": signal.symbol,
                "signal_type": signal.signal_type.value,
                "reason": signal.reason,
                "price": price,
                "candle_at": signal.timestamp.isoformat() if signal.timestamp else None,
                "acted": acted,
            }
        ).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Could not push signal: {exc}")


def is_trading_enabled(settings: Settings, default: bool = True) -> bool:
    """Reads the dashboard kill switch.

    `default` is what to assume when Supabase is unreachable or unconfigured. It defaults to
    True so that an unconfigured bot behaves exactly as it did before this table existed —
    but a live deployment that relies on the kill switch should pass default=False so a
    network outage pauses trading rather than silently ignoring the switch.
    """
    client = get_client(settings)
    if client is None:
        return default
    try:
        response = (
            client.table("bot_controls").select("trading_enabled").eq("id", 1).maybe_single().execute()
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Could not read kill switch, assuming trading_enabled={default}: {exc}")
        return default

    if response is None or not response.data:
        return default
    return bool(response.data["trading_enabled"])
