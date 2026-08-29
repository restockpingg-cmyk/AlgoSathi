# AlgoSathi

A personal algo trading bot for Indian equities (NSE), connecting to **Upstox** for market
data and order execution. Ships with a safe **paper-trading** mode (simulated fills, no
real orders) and a pluggable strategy interface, with an example fast/slow SMA crossover
strategy wired end-to-end.

## Project layout

```
algosathi/
  core/          shared vocabulary: Candle, Signal, OrderRequest, Fill, Position
  strategy/      Strategy interface + SmaCrossoverStrategy (pure functions of candle history)
  broker/        BrokerAdapter interface + PaperBroker (simulated) + UpstoxBroker (real orders)
  market_data/   historical candle fetching from Upstox + symbol->instrument_key lookup
  risk/          RiskManager: position sizing, max daily loss, max open positions
  persistence/   SQLite trade log (SQLAlchemy)
  auth/          Upstox OAuth2 login flow + daily CLI login helper
  runner.py      wires everything together; paper-mode replay + live polling loop
scripts/
  generate_sample_data.py   synthetic OHLC CSV for demoing the runner with no API key needed
  report_pnl.py             realized P&L + open position summary from the trade log
config/settings.yaml        strategy/risk/mode config (non-secret)
.env                         secrets: Upstox API key/secret, live-trading confirmation gate
```

`runner.py` is the only place that picks a concrete broker/data-source — strategy, risk, and
persistence code never know or care whether they're running in paper or live mode.

## Setup

```
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
```

## Try it now (paper mode, no Upstox account needed)

```
.venv\Scripts\python scripts\generate_sample_data.py
.venv\Scripts\python -m algosathi.runner --csv data\sample\infy_sample.csv
.venv\Scripts\python scripts\report_pnl.py
```

This replays a synthetic candle series through the strategy → risk → paper-broker pipeline,
logs each simulated fill, and prints a P&L summary read back from SQLite.

## Running tests

```
.venv\Scripts\python -m pytest
```

## Configuration

Edit `config/settings.yaml` for strategy parameters, risk limits, symbol, and mode
(`paper` or `live`). Copy `.env.example` to `.env` for secrets — **never commit `.env`**.

## Going live with real Upstox data/orders

This requires manual setup that only you can do:

1. **Register a developer app** at the [Upstox Developer Console](https://upstox.com/developer/apps)
   to get an `API Key` and `API Secret`. Set a `Redirect URI` there matching `.env`
   (a placeholder like `https://127.0.0.1/callback` is fine — Upstox doesn't need it
   reachable, only matching at redirect time).
2. Put those values in `.env` (copy from `.env.example`).
3. **Log in daily** — Upstox access tokens always expire at 3:30 AM IST, so each trading day,
   before running the bot, run:
   ```
   .venv\Scripts\python -m algosathi.auth.cli_login
   ```
   Follow the printed URL, log in, and paste back the `code` from the redirected URL.
4. With a valid cached token, `python -m algosathi.runner` (no `--csv`) pulls real historical
   candles from Upstox and runs the live polling loop, still in **paper mode** by default —
   this proves the pipeline against real market data with zero real orders.
5. **To place real orders**, both of these must be true at once (deliberately two separate
   knobs, since real money is at risk):
   - `mode: live` in `config/settings.yaml`
   - `LIVE_TRADING_CONFIRMED=true` in `.env`

   Start with the smallest possible order size and watch the Upstox app side-by-side before
   trusting the bot unattended.

Check Upstox's current API docs for rate limits and pricing before relying on the defaults
here — they're controlled by Upstox and can change independently of this codebase. F&O
(lot sizes, segment activation) is out of scope for v1; this targets NSE cash equities.
