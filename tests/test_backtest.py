from datetime import datetime, timedelta

import pandas as pd

from algosathi.backtest import run_backtest
from algosathi.config import RiskConfig


def make_candles(closes: list[float]) -> pd.DataFrame:
    start = datetime(2026, 1, 1, 9, 15)
    return pd.DataFrame(
        {
            "timestamp": [start + timedelta(minutes=5 * i) for i in range(len(closes))],
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1000] * len(closes),
        }
    )


DEFINITION = {
    "entry": {
        "operator": "and",
        "conditions": [
            {
                "left": {"indicator": "sma", "period": 2},
                "op": "crosses_above",
                "right": {"indicator": "sma", "period": 4},
            }
        ],
    },
    "exit": {
        "operator": "and",
        "conditions": [
            {
                "left": {"indicator": "sma", "period": 2},
                "op": "crosses_below",
                "right": {"indicator": "sma", "period": 4},
            }
        ],
    },
}


def test_profitable_round_trip():
    downtrend = list(range(20, 9, -1))
    uptrend = list(range(10, 40))
    downtrend_again = list(range(39, 9, -1))
    candles = make_candles(downtrend + uptrend + downtrend_again)

    risk_config = RiskConfig(order_quantity=1, max_daily_loss=100_000, max_open_positions=1)
    result = run_backtest(DEFINITION, "TEST", candles, risk_config, starting_cash=100_000)

    assert result.total_trades == 2  # one BUY, one EXIT
    assert result.realized_pnl > 0  # bought low in the uptrend leg, sold high before the drop
    assert result.win_rate == 1.0
    assert len(result.equity_curve) == 1  # one closed (SELL) trade


def test_no_signals_produces_empty_result():
    candles = make_candles([100.0] * 10)  # flat, no crossovers ever
    risk_config = RiskConfig(order_quantity=1, max_daily_loss=100_000, max_open_positions=1)
    result = run_backtest(DEFINITION, "TEST", candles, risk_config)

    assert result.total_trades == 0
    assert result.realized_pnl == 0.0
    assert result.win_rate == 0.0
    assert result.max_drawdown == 0.0
