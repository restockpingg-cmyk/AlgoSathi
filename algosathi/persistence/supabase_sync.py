from __future__ import annotations

from loguru import logger

from algosathi.config import Settings
from algosathi.core.enums import Mode
from algosathi.core.models import Fill

_client = None
_client_url = None


def _get_client(settings: Settings):
    global _client, _client_url
    url = settings.secrets.supabase_url
    key = settings.secrets.supabase_service_key
    if not url or not key:
        return None
    if _client is None or _client_url != url:
        from supabase import create_client

        _client = create_client(url, key)
        _client_url = url
    return _client


def push_fill(fill: Fill, mode: Mode, settings: Settings) -> None:
    """Best-effort sync of one fill to Supabase for the online dashboard. Never raises —
    a Supabase/network hiccup must not interrupt the trading loop."""
    client = _get_client(settings)
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
