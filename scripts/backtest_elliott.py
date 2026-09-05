"""Backtests the Elliott Wave (wave-3) strategy against candles from Supabase or a local CSV.

Elliott Wave can't be expressed in the web builder's JSON condition-tree format — it reasons
about swing structure, not per-bar indicator comparisons — so it gets its own CLI rather than
going through scripts/backtest_cli.py.

    .venv\\Scripts\\python scripts\\backtest_elliott.py --symbol INFY --interval 5 --zigzag-pct 0.5
    .venv\\Scripts\\python scripts\\backtest_elliott.py --symbol INFY --csv data\\sample\\infy_sample.csv
"""

from __future__ import annotations

import argparse

import pandas as pd

from algosathi.backtest import run_strategy_backtest
from algosathi.config import RiskConfig, get_settings
from algosathi.persistence.supabase_candles import fetch_candles
from algosathi.strategy.elliott_wave import ElliottWaveStrategy, find_pivots


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest the Elliott Wave strategy")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--interval", type=int, default=5, help="candle interval in minutes")
    parser.add_argument("--csv", default=None, help="read candles from this CSV instead of Supabase")
    parser.add_argument("--zigzag-pct", type=float, default=0.5, help="swing reversal threshold, percent")
    parser.add_argument("--min-retracement", type=float, default=0.382)
    parser.add_argument("--max-retracement", type=float, default=0.786)
    parser.add_argument("--target-extension", type=float, default=1.618)
    parser.add_argument("--starting-cash", type=float, default=100_000.0)
    parser.add_argument("--order-quantity", type=int, default=1)
    parser.add_argument("--max-daily-loss", type=float, default=5_000.0)
    parser.add_argument("--max-open-positions", type=int, default=1)
    parser.add_argument("--show-trades", action="store_true")
    args = parser.parse_args()

    if args.csv:
        candles = (
            pd.read_csv(args.csv, parse_dates=["timestamp"])
            .sort_values("timestamp")
            .reset_index(drop=True)
        )
    else:
        candles = fetch_candles(args.symbol, args.interval, get_settings())

    if candles.empty:
        raise SystemExit(f"No candles found for {args.symbol} ({args.interval}m)")

    strategy = ElliottWaveStrategy(
        symbol=args.symbol,
        zigzag_pct=args.zigzag_pct,
        min_retracement=args.min_retracement,
        max_retracement=args.max_retracement,
        target_extension=args.target_extension,
    )
    risk_config = RiskConfig(
        order_quantity=args.order_quantity,
        max_daily_loss=args.max_daily_loss,
        max_open_positions=args.max_open_positions,
    )
    result = run_strategy_backtest(
        strategy, args.symbol, candles, risk_config, args.starting_cash
    )

    pivots = find_pivots(candles, args.zigzag_pct)
    start, end = candles["timestamp"].iloc[0], candles["timestamp"].iloc[-1]

    print(f"Symbol:         {args.symbol} ({args.interval}m)")
    print(f"Window:         {start} -> {end}  ({len(candles)} candles)")
    print(f"Zig-zag:        {args.zigzag_pct}%  ->  {len(pivots)} swing pivots")
    print(f"Total trades:   {result.total_trades}")
    print(f"Realized P&L:   {result.realized_pnl:.2f}")
    print(f"Win rate:       {result.win_rate:.1%}")
    print(f"Max drawdown:   {result.max_drawdown:.2f}")

    if args.show_trades:
        print()
        for fill in result.trades:
            print(f"  {fill.timestamp}  {fill.side:<4}  {fill.quantity} @ {fill.price:.2f}")


if __name__ == "__main__":
    main()
