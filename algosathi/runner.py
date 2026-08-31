from __future__ import annotations

import argparse
import time
from datetime import datetime, time as dtime

import pandas as pd
from loguru import logger

from algosathi.broker.base import BrokerAdapter
from algosathi.broker.paper_broker import PaperBroker
from algosathi.config import Settings, get_settings
from algosathi.core.enums import Mode
from algosathi.logging_setup import setup_logging
from algosathi.persistence.db import get_session_factory, record_fill
from algosathi.persistence.supabase_strategies import fetch_active_strategy
from algosathi.persistence.supabase_sync import push_fill
from algosathi.risk.risk_manager import RiskManager
from algosathi.simulation import act_on_signal, simulate_candles
from algosathi.strategy.base import Strategy
from algosathi.strategy.rule_strategy import RuleStrategy
from algosathi.strategy.sma_crossover import SmaCrossoverStrategy

MARKET_OPEN = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)


def is_market_open(now: datetime) -> bool:
    return now.weekday() < 5 and MARKET_OPEN <= now.time() <= MARKET_CLOSE


def build_strategy(settings: Settings) -> Strategy:
    cfg = settings.yaml.strategy
    symbol = settings.yaml.symbol

    if cfg.source == "supabase":
        row = fetch_active_strategy(symbol, settings)
        if row is None:
            raise RuntimeError(
                f"strategy.source is 'supabase' but no active strategy found for symbol "
                f"{symbol!r} in the strategies table"
            )
        return RuleStrategy(symbol=symbol, definition=row["definition"])

    if cfg.name == "sma_crossover":
        return SmaCrossoverStrategy(
            symbol=symbol,
            fast_period=cfg.fast_period,
            slow_period=cfg.slow_period,
            ma_type=cfg.ma_type,
        )
    raise ValueError(f"unknown strategy: {cfg.name}")


def build_risk_manager(settings: Settings) -> RiskManager:
    cfg = settings.yaml.risk
    return RiskManager(
        order_quantity=cfg.order_quantity,
        max_daily_loss=cfg.max_daily_loss,
        max_open_positions=cfg.max_open_positions,
    )


def build_broker(settings: Settings) -> BrokerAdapter:
    settings.require_live_trading_authorized()
    session_factory = get_session_factory()

    def trade_recorder(fill):
        record_fill(session_factory, fill, settings.mode)
        push_fill(fill, settings.mode, settings)

    if settings.mode == Mode.LIVE:
        # Imported lazily so paper-mode users never need Upstox credentials configured.
        from algosathi.auth.upstox_auth import get_valid_token
        from algosathi.broker.upstox_broker import UpstoxBroker

        token = get_valid_token(settings)
        return UpstoxBroker(access_token=token, trade_recorder=trade_recorder)

    return PaperBroker(starting_cash=settings.yaml.paper.starting_cash, trade_recorder=trade_recorder)


def run_replay(settings: Settings, candles: pd.DataFrame) -> PaperBroker:
    """Feed a historical OHLC DataFrame through the strategy/risk/broker pipeline one candle
    at a time, filling orders at the *next* candle's open to avoid look-ahead bias. Used for
    paper-mode dry runs against a CSV of historical or sample data."""
    setup_logging()
    strategy = build_strategy(settings)
    risk_manager = build_risk_manager(settings)
    broker = build_broker(settings)
    assert isinstance(broker, PaperBroker), "run_replay only supports paper mode"

    symbol = settings.yaml.symbol
    logger.info(f"Starting replay for {symbol} over {len(candles)} candles")

    simulate_candles(strategy, risk_manager, broker, symbol, candles)

    logger.info(
        f"Replay complete. realized_pnl={broker.realized_pnl:.2f} "
        f"open_position={broker.get_position(symbol)} funds={broker.get_funds():.2f}"
    )
    return broker


def run_live(settings: Settings) -> None:
    """Poll for the latest candle on a fixed interval during market hours, feeding it through
    the same strategy/risk/broker pipeline as run_replay."""
    from algosathi.market_data.upstox_historical import UpstoxHistoricalProvider

    setup_logging()
    strategy = build_strategy(settings)
    risk_manager = build_risk_manager(settings)
    broker = build_broker(settings)
    symbol = settings.yaml.symbol

    from algosathi.auth.upstox_auth import get_valid_token

    token = get_valid_token(settings)
    provider = UpstoxHistoricalProvider(access_token=token)

    logger.info(f"Starting live loop for {symbol} in {settings.mode.value} mode")
    while True:
        now = datetime.now()
        if not is_market_open(now):
            logger.info("Market closed, sleeping...")
            time.sleep(settings.yaml.polling_interval_seconds)
            continue

        candles = provider.get_recent_candles(
            symbol=symbol,
            exchange=settings.yaml.exchange,
            interval_minutes=settings.yaml.candle_interval_minutes,
        )
        signal = strategy.on_candles(candles)
        if signal is not None:
            latest_close = float(candles.iloc[-1]["close"])
            if isinstance(broker, PaperBroker):
                broker.update_market_price(symbol, latest_close)
            act_on_signal(signal, symbol, risk_manager, broker, getattr(broker, "realized_pnl", 0.0))

        time.sleep(settings.yaml.polling_interval_seconds)


def _load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["timestamp"])
    return df.sort_values("timestamp").reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="AlgoSathi runner")
    parser.add_argument(
        "--csv",
        help="Path to a historical OHLC CSV to replay in paper mode (columns: "
        "timestamp,open,high,low,close,volume). If omitted, runs the live polling loop.",
    )
    args = parser.parse_args()

    settings = get_settings()

    if args.csv:
        candles = _load_csv(args.csv)
        run_replay(settings, candles)
    else:
        run_live(settings)


if __name__ == "__main__":
    main()
