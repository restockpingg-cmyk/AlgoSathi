from __future__ import annotations

import argparse
import time
from functools import partial
from datetime import datetime, time as dtime

import pandas as pd
from loguru import logger

from algosathi.broker.base import BrokerAdapter
from algosathi.broker.paper_broker import PaperBroker
from algosathi.config import Settings, get_settings
from algosathi.core.enums import Mode, OrderType, Side, SignalType
from algosathi.core.models import Fill, OrderRequest, Signal
from algosathi.logging_setup import setup_logging
from algosathi.persistence.db import get_session_factory, record_fill
from algosathi.risk.day_ledger import open_positions, realized_pnl_today
from algosathi.persistence.supabase_status import is_trading_enabled, push_signal, push_status
from algosathi.persistence.supabase_strategies import fetch_active_strategy
from algosathi.persistence.supabase_sync import push_fill
from algosathi.risk.position_guard import PositionGuard
from algosathi.risk.risk_manager import RiskManager
from algosathi.simulation import act_on_signal, simulate_candles
from algosathi.strategy.base import Strategy
from algosathi.symbol_worker import SymbolWorker
from algosathi.strategy.elliott_wave import ElliottWaveStrategy
from algosathi.strategy.rule_strategy import RuleStrategy
from algosathi.strategy.sma_crossover import SmaCrossoverStrategy

MARKET_OPEN = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)


def is_market_open(now: datetime) -> bool:
    return now.weekday() < 5 and MARKET_OPEN <= now.time() <= MARKET_CLOSE


def build_strategy_from_row(symbol: str, row: dict) -> Strategy:
    """Builds a strategy from a `strategies` table row.

    A saved strategy is either a rule tree from the visual builder (strategy_type 'rule') or
    one of the built-in classes parameterised by the `params` column — the builder's condition
    schema can't express something like Elliott Wave, which reasons about swing structure
    rather than per-bar indicator comparisons.
    """
    strategy_type = row.get("strategy_type") or "rule"
    params = row.get("params") or {}

    if strategy_type == "rule":
        return RuleStrategy(symbol=symbol, definition=row["definition"])
    if strategy_type == "elliott_wave":
        return ElliottWaveStrategy(symbol=symbol, **params)
    if strategy_type == "sma_crossover":
        return SmaCrossoverStrategy(symbol=symbol, **params)
    raise ValueError(f"unknown strategy_type: {strategy_type!r}")


def build_strategy(settings: Settings, symbol: str | None = None) -> Strategy:
    cfg = settings.yaml.strategy
    symbol = symbol or settings.yaml.symbol

    if cfg.source == "supabase":
        row = fetch_active_strategy(symbol, settings)
        if row is None:
            raise RuntimeError(
                f"strategy.source is 'supabase' but no active strategy found for symbol "
                f"{symbol!r} in the strategies table"
            )
        return build_strategy_from_row(symbol, row)

    if cfg.name == "sma_crossover":
        return SmaCrossoverStrategy(
            symbol=symbol,
            fast_period=cfg.fast_period,
            slow_period=cfg.slow_period,
            ma_type=cfg.ma_type,
        )
    if cfg.name == "elliott_wave":
        return ElliottWaveStrategy(symbol=symbol)
    raise ValueError(f"unknown strategy: {cfg.name}")


def describe_strategy(strategy: Strategy) -> str:
    """Human-readable label for the dashboard heartbeat."""
    return type(strategy).__name__


def build_risk_manager(settings: Settings) -> RiskManager:
    cfg = settings.yaml.risk
    return RiskManager(
        order_quantity=cfg.order_quantity,
        max_daily_loss=cfg.max_daily_loss,
        max_open_positions=cfg.max_open_positions,
        capital_per_trade=cfg.capital_per_trade,
        lot_size=cfg.lot_size,
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
        return UpstoxBroker(
            access_token=token,
            exchange=settings.yaml.exchange,
            trade_recorder=trade_recorder,
        )

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

    simulate_candles(
        strategy, risk_manager, broker, symbol, candles, guard=PositionGuard(settings.yaml.risk.exits)
    )

    logger.info(
        f"Replay complete. realized_pnl={broker.realized_pnl:.2f} "
        f"open_position={broker.get_position(symbol)} funds={broker.get_funds():.2f}"
    )
    return broker


def run_live(settings: Settings) -> None:
    """Poll every symbol in the universe on a fixed interval during market hours, feeding each
    through the same strategy/risk/broker pipeline as run_replay.

    Account-level limits are deliberately shared across symbols rather than per-symbol: a
    universe scan that gave every symbol its own max_open_positions and its own daily-loss
    budget would take on N times the risk the config asked for.
    """
    from algosathi.market_data.upstox_historical import UpstoxHistoricalProvider
    from algosathi.auth.upstox_auth import get_valid_token

    setup_logging()
    risk_manager = build_risk_manager(settings)
    broker = build_broker(settings)
    session_factory = get_session_factory()
    provider = UpstoxHistoricalProvider(access_token=get_valid_token(settings))

    universe = settings.yaml.universe
    strategy_row = None
    if settings.yaml.strategy.source == "supabase":
        # Fetched once and applied across the universe: the point of a scan is one strategy
        # over many symbols, not a different strategy per symbol.
        strategy_row = fetch_active_strategy(settings.yaml.symbol, settings)
        if strategy_row is None:
            raise RuntimeError(
                f"strategy.source is 'supabase' but no active strategy found for "
                f"{settings.yaml.symbol!r} in the strategies table"
            )

    workers: list[SymbolWorker] = []
    for symbol in universe:
        strategy = (
            build_strategy_from_row(symbol, strategy_row)
            if strategy_row is not None
            else build_strategy(settings, symbol)
        )
        worker = SymbolWorker(
            symbol=symbol,
            strategy=strategy,
            guard=PositionGuard(settings.yaml.risk.exits),
            broker=broker,
            risk_manager=risk_manager,
            quote=partial(provider.get_ltp, symbol, settings.yaml.exchange),
        )
        worker.restore()
        workers.append(worker)

    strategy_name = describe_strategy(workers[0].strategy) if workers else "none"
    logger.info(
        f"Starting live loop in {settings.mode.value} mode ({strategy_name}) over "
        f"{len(workers)} symbol(s): {', '.join(universe)}"
    )

    def heartbeat(market_open: bool, error: str | None = None) -> None:
        """One status row per symbol, so the dashboard can tell which symbol is holding what
        rather than showing a single blurred total."""
        for worker in workers:
            position = broker.get_position(worker.symbol)
            push_status(
                settings,
                symbol=worker.symbol,
                mode=settings.mode.value,
                strategy_name=strategy_name,
                market_open=market_open,
                last_candle_at=(
                    worker.last_candle_at.isoformat() if worker.last_candle_at is not None else None
                ),
                last_price=worker.last_price,
                position_qty=position.quantity,
                position_avg_price=position.avg_price if position.quantity else None,
                cash=broker.get_funds(),
                realized_pnl=realized_pnl_today(session_factory, settings.mode),
                unrealized_pnl=worker.unrealized_pnl(),
                last_error=error or worker.last_error,
            )

    while True:
        now = datetime.now()
        if not is_market_open(now):
            logger.info("Market closed, sleeping...")
            heartbeat(market_open=False)
            time.sleep(settings.yaml.polling_interval_seconds)
            continue

        # Read once per cycle, not once per symbol: the kill switch and the day's P&L are
        # account-wide, and re-reading them mid-cycle would let symbols disagree about
        # whether trading is still allowed.
        entries_allowed = is_trading_enabled(settings)
        pnl_today = realized_pnl_today(session_factory, settings.mode)

        for worker in workers:
            try:
                candles = provider.get_recent_candles(
                    symbol=worker.symbol,
                    exchange=settings.yaml.exchange,
                    interval_minutes=settings.yaml.candle_interval_minutes,
                )
                if candles.empty:
                    continue
                signal = worker.poll(candles, now, pnl_today, entries_allowed)
                if signal is not None:
                    push_signal(settings, signal, worker.last_price, acted=worker.acted)
                worker.last_error = None
            except Exception as exc:  # noqa: BLE001 — one bad symbol must not stop the rest
                logger.exception(f"{worker.symbol}: poll failed")
                worker.last_error = f"{type(exc).__name__}: {exc}"

        heartbeat(market_open=True)
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
