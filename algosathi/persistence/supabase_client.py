from __future__ import annotations

from algosathi.config import Settings

_client = None
_client_url = None


def get_client(settings: Settings):
    """Returns a cached service-role Supabase client, or None if not configured."""
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
