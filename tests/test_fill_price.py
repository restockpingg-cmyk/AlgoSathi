"""Backtests fill at the next candle's open; live paper used to fill at the close of the
candle that produced the signal. Both claim to be "the price you'd have got", but the second
is a full candle plus a poll interval stale, so paper drifted from the backtest for reasons
that had nothing to do with the strategy.

These pin down the fix: fill at the price available now, and read the live quote correctly.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest

from algosathi.broker.paper_broker import PaperBroker
from algosathi.config import ExitRulesConfig
from algosathi.core.enums import SignalType
from algosathi.core.models import Signal
from algosathi.market_data import upstox_historical as uh
from algosathi.risk.position_guard import PositionGuard
from algosathi.risk.risk_manager import RiskManager
from algosathi.strategy.base import Strategy
from algosathi.symbol_worker import SymbolWorker


class AlwaysBuy(Strategy):
    def on_candles(self, candles):
        return Signal(
            symbol="INFY",
            signal_type=SignalType.BUY,
            reason="test",
            timestamp=candles["timestamp"].iloc[-1],
        )


def candles(closes: list[float]) -> pd.DataFrame:
    start = datetime(2026, 3, 10, 10, 0)
    return pd.DataFrame(
        {
            "timestamp": [start + timedelta(minutes=5 * i) for i in range(len(closes))],
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [100] * len(closes),
        }
    )


def worker(broker, quote=None) -> SymbolWorker:
    return SymbolWorker(
        symbol="INFY",
        strategy=AlwaysBuy(),
        guard=PositionGuard(ExitRulesConfig()),
        broker=broker,
        risk_manager=RiskManager(order_quantity=1, max_daily_loss=5000.0, max_open_positions=1),
        quote=quote,
    )


def test_fills_at_the_live_price_not_the_stale_candle_close():
    broker = PaperBroker(starting_cash=100_000.0)
    w = worker(broker, quote=lambda: 1010.0)

    w.poll(candles([1000.0, 1000.0]), datetime(2026, 3, 10, 10, 6), 0.0, entries_allowed=True)

    assert broker.get_position("INFY").avg_price == 1010.0


def test_falls_back_to_the_candle_close_when_no_quote_is_available():
    broker = PaperBroker(starting_cash=100_000.0)
    w = worker(broker, quote=None)

    w.poll(candles([1000.0, 1000.0]), datetime(2026, 3, 10, 10, 6), 0.0, entries_allowed=True)

    assert broker.get_position("INFY").avg_price == 1000.0


def test_a_failing_quote_does_not_skip_the_trade():
    """A stale price is worse than a live one, but skipping an entry entirely because a quote
    call blipped is worse still — especially for an exit."""
    broker = PaperBroker(starting_cash=100_000.0)

    def broken_quote():
        raise ConnectionError("quote service down")

    w = worker(broker, quote=broken_quote)
    w.poll(candles([1000.0, 1000.0]), datetime(2026, 3, 10, 10, 6), 0.0, entries_allowed=True)

    assert broker.get_position("INFY").quantity == 1
    assert broker.get_position("INFY").avg_price == 1000.0


def test_no_quote_call_is_made_when_there_is_no_signal():
    """A universe scan must not spend a quote call per symbol per poll just to sit still."""
    calls = []

    class NeverTrade(Strategy):
        def on_candles(self, candles):
            return None

    broker = PaperBroker(starting_cash=100_000.0)
    w = SymbolWorker(
        symbol="INFY",
        strategy=NeverTrade(),
        guard=PositionGuard(ExitRulesConfig()),
        broker=broker,
        risk_manager=RiskManager(order_quantity=1, max_daily_loss=5000.0, max_open_positions=1),
        quote=lambda: calls.append(1) or 1010.0,
    )
    w.poll(candles([1000.0, 1000.0]), datetime(2026, 3, 10, 10, 6), 0.0, entries_allowed=True)

    assert calls == []


# --- LTP parsing --------------------------------------------------------------


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture(autouse=True)
def stub_lookup(monkeypatch):
    monkeypatch.setattr(uh, "resolve_instrument_key", lambda *a, **k: "NSE_EQ|INE009A01021")


def test_ltp_is_read_despite_the_response_key_differing_from_the_request(monkeypatch):
    """Upstox keys the response by EXCHANGE:TRADINGSYMBOL but the request uses
    EXCHANGE|token, so looking it up by the key we sent finds nothing."""
    monkeypatch.setattr(
        uh.requests,
        "get",
        lambda *a, **k: FakeResponse(
            {
                "data": {
                    "NSE_EQ:INFY": {
                        "last_price": 1144.5,
                        "instrument_token": "NSE_EQ|INE009A01021",
                    }
                }
            }
        ),
    )
    provider = uh.UpstoxHistoricalProvider(access_token="t")
    assert provider.get_ltp("INFY", "NSE_EQ") == 1144.5


def test_ltp_returns_none_when_the_quote_is_empty(monkeypatch):
    monkeypatch.setattr(uh.requests, "get", lambda *a, **k: FakeResponse({"data": {}}))
    provider = uh.UpstoxHistoricalProvider(access_token="t")
    assert provider.get_ltp("INFY", "NSE_EQ") is None


def test_an_expired_token_fails_fast_instead_of_retrying(monkeypatch):
    """A dead token will not recover, and retrying buries the one actionable cause under a
    RetryError three attempts later."""
    calls = []

    def unauthorized(*a, **k):
        calls.append(1)
        return FakeResponse({"status": "error"}, status_code=401)

    monkeypatch.setattr(uh.requests, "get", unauthorized)
    provider = uh.UpstoxHistoricalProvider(access_token="stale")

    with pytest.raises(uh.AuthRequiredError, match="cli_login"):
        provider.get_ltp("INFY", "NSE_EQ")
    assert len(calls) == 1
