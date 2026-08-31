from __future__ import annotations

from loguru import logger

from algosathi.config import Settings
from algosathi.core.enums import Mode
from algosathi.core.models import Fill
from algosathi.persistence.supabase_client import get_client


def push_fill(fill: Fill, mode: Mode, settings: Settings) -> None:
    """Best-effort sync of one fill to Supabase for the online dashboard. Never raises —
    a Supabase/network hiccup must not interrupt the trading loop."""
    client = get_client(settings)
    if client is None:
        return
    try:
        client.table("trades").insert(
            {
                "order_id": fill.order_id,
                "symbol": fill.symbol,
                "side": fill.side.value,
                "quantity": fill.quantity,
                "price": fill.price,
                "timestamp": fill.timestamp.isoformat(),
                "mode": mode.value,
            }
        ).execute()
    except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
        logger.warning(f"Supabase sync failed for fill {fill.order_id}: {exc}")
