from __future__ import annotations

import argparse
import time
from datetime import datetime, time as dtime

import pandas as pd
from loguru import logger

from algosathi.broker.base import BrokerAdapter
from algosathi.broker.paper_broker import PaperBroker
from algosathi.config import Settings, get_settings
from algosathi.core.enums import Mode, Side, SignalType
from algosathi.core.models import Signal
from algosathi.logging_setup import setup_logging
from algosathi.persistence.db import get_session_factory, record_fill
from algosathi.persistence.supabase_status import is_trading_enabled, push_signal, push_status
from algosathi.persistence.supabase_strategies import fetch_active_strategy
from algosathi.persistence.supabase_sync import push_fill
from algosathi.risk.position_guard import PositionGuard
from algosathi.risk.risk_manager import RiskManager
from algosathi.simulation import act_on_signal, simulate_candles
from algosathi.strategy.base import Strategy
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

    simulate_candles(
        strategy, risk_manager, broker, symbol, candles, guard=PositionGuard(settings.yaml.risk.exits)
    )

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

    guard = PositionGuard(settings.yaml.risk.exits)
    strategy_name = describe_strategy(strategy)
    logger.info(f"Starting live loop for {symbol} in {settings.mode.value} mode ({strategy_name})")

    def heartbeat(**extra) -> None:
        """Report where the bot is on every loop, so the dashboard can tell 'flat on purpose'
        apart from 'the process died'."""
        position = broker.get_position(symbol)
        push_status(
            settings,
            mode=settings.mode.value,
            symbol=symbol,
            strategy_name=strategy_name,
            position_qty=position.quantity,
            position_avg_price=position.avg_price if position.quantity else None,
            cash=broker.get_funds(),
            realized_pnl=getattr(broker, "realized_pnl", 0.0),
            **extra,
        )

    while True:
        now = datetime.now()
        if not is_market_open(now):
            logger.info("Market closed, sleeping...")
            heartbeat(market_open=False)
            time.sleep(settings.yaml.polling_interval_seconds)
            continue

        try:
            candles = provider.get_recent_candles(
                symbol=symbol,
                exchange=settings.yaml.exchange,
                interval_minutes=settings.yaml.candle_interval_minutes,
            )
            latest_close = float(candles.iloc[-1]["close"])
            if isinstance(broker, PaperBroker):
                broker.update_market_price(symbol, latest_close)

            position = broker.get_position(symbol)
            unrealized = (
                (latest_close - position.avg_price) * position.quantity if position.quantity else 0.0
            )

            # Stops are checked before the strategy is even consulted, so a stop loss or the
            # square-off always wins over a strategy signal on the same candle.
            signal = None
            if guard.is_armed:
                last = candles.iloc[-1]
                triggered = guard.check(
                    latest_close, now, low=float(last["low"]), high=float(last["high"])
                )
                if triggered is not None:
                    signal = Signal(
                        symbol=symbol,
                        signal_type=SignalType.EXIT,
                        reason=triggered.reason,
                        timestamp=candles.iloc[-1]["timestamp"],
                    )
                    logger.warning(f"{symbol}: {triggered.reason}")

            if signal is None:
                signal = strategy.on_candles(candles)
                if signal is not None and signal.signal_type is SignalType.BUY:
                    allowed, why = guard.entry_allowed(now)
                    if not allowed:
                        logger.info(f"{symbol}: BUY skipped — {why}")
                        signal = None

            fill = None
            if signal is not None:
                # The dashboard kill switch only blocks *opening* risk. An exit must always be
                # allowed through, otherwise flipping the switch would trap an open position.
                blocked = signal.signal_type is SignalType.BUY and not is_trading_enabled(settings)
                if blocked:
                    logger.warning(f"{symbol}: BUY suppressed — trading is disabled from the dashboard")
                else:
                    fill = act_on_signal(
                        signal,
                        symbol,
                        risk_manager,
                        broker,
                        getattr(broker, "realized_pnl", 0.0),
                        latest_close,
                    )
                    if fill is not None:
                        if fill.side == Side.BUY:
                            guard.on_entry(fill.price)
                        else:
                            guard.on_exit()
                push_signal(settings, signal, latest_close, acted=fill is not None)

            heartbeat(
                market_open=True,
                last_candle_at=candles.iloc[-1]["timestamp"].isoformat(),
                last_price=latest_close,
                unrealized_pnl=unrealized,
                last_error=None,
            )
        except Exception as exc:  # noqa: BLE001 — one bad poll must not end the session
            logger.exception("Live loop iteration failed")
            heartbeat(market_open=True, last_error=f"{type(exc).__name__}: {exc}")

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
