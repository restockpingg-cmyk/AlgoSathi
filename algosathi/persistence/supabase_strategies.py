from __future__ import annotations

from typing import Any

from algosathi.config import Settings
from algosathi.persistence.supabase_client import get_client


def fetch_active_strategy(symbol: str, settings: Settings) -> dict[str, Any] | None:
    """Returns the active strategy row for `symbol` from Supabase, or None if unconfigured
    or not found. Raises on a genuine Supabase error (unlike push_fill's best-effort sync,
    a missing/broken strategy source should fail loudly rather than silently do nothing)."""
    client = get_client(settings)
    if client is None:
        raise RuntimeError(
            "strategy.source is 'supabase' but SUPABASE_URL/SUPABASE_SERVICE_KEY are not "
            "set in .env"
        )

    response = (
        client.table("strategies")
        .select("*")
        .eq("symbol", symbol)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    return rows[0] if rows else None
