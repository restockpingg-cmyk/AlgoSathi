from __future__ import annotations

import json
from pathlib import Path

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

INSTRUMENT_SEARCH_URL = "https://api.upstox.com/v2/instruments/search"

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
CACHE_PATH = DATA_DIR / "instrument_cache.json"


def _load_cache() -> dict[str, str]:
    if not CACHE_PATH.exists():
        return {}
    return json.loads(CACHE_PATH.read_text(encoding="utf-8"))


def _save_cache(cache: dict[str, str]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def resolve_instrument_key(access_token: str, symbol: str, exchange: str, segment: str) -> str:
    """Resolve a trading symbol (e.g. 'INFY' on NSE/EQ) to Upstox's instrument_key
    (e.g. 'NSE_EQ|INE009A01021'), caching results locally since they rarely change."""
    cache_key = f"{exchange}:{segment}:{symbol}"
    cache = _load_cache()
    if cache_key in cache:
        return cache[cache_key]

    response = requests.get(
        INSTRUMENT_SEARCH_URL,
        headers={"Accept": "application/json", "Authorization": f"Bearer {access_token}"},
        params={"query": symbol, "exchanges": exchange, "segments": segment},
        timeout=15,
    )
    response.raise_for_status()
    results = response.json().get("data", [])

    match = next((r for r in results if r.get("trading_symbol") == symbol), None)
    if match is None:
        raise ValueError(f"could not resolve instrument_key for {symbol} on {exchange}/{segment}")

    instrument_key = match["instrument_key"]
    cache[cache_key] = instrument_key
    _save_cache(cache)
    return instrument_key
