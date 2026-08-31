"""Runs a strategy JSON definition (the same format the web builder produces) against a
local OHLC CSV and prints backtest metrics. Useful for sanity-checking RuleStrategy/backtest.py
without going through the web UI.

    .venv\\Scripts\\python scripts\\backtest_cli.py --strategy strategy.json --csv data\\sample\\infy_sample.csv --symbol INFY
"""

from __future__ import annotations

import argparse
import json

import pandas as pd

from algosathi.backtest import run_backtest
from algosathi.config import RiskConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest a strategy JSON against a CSV")
    parser.add_argument("--strategy", required=True, help="path to a strategy definition JSON file")
    parser.add_argument("--csv", required=True, help="path to an OHLC CSV (timestamp,open,high,low,close,volume)")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--starting-cash", type=float, default=100_000.0)
    parser.add_argument("--order-quantity", type=int, default=1)
    parser.add_argument("--max-daily-loss", type=float, default=5_000.0)
    parser.add_argument("--max-open-positions", type=int, default=1)
    args = parser.parse_args()

    with open(args.strategy, "r", encoding="utf-8") as f:
        definition = json.load(f)

    candles = pd.read_csv(args.csv, parse_dates=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    risk_config = RiskConfig(
        order_quantity=args.order_quantity,
        max_daily_loss=args.max_daily_loss,
        max_open_positions=args.max_open_positions,
    )
    result = run_backtest(definition, args.symbol, candles, risk_config, args.starting_cash)

    print(f"Total trades:   {result.total_trades}")
    print(f"Realized P&L:   {result.realized_pnl:.2f}")
    print(f"Win rate:       {result.win_rate:.1%}")
    print(f"Max drawdown:   {result.max_drawdown:.2f}")


if __name__ == "__main__":
    main()
