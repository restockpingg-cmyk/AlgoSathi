"""Places ONE real order to prove the live order path works, then closes it immediately.

Every test of UpstoxBroker uses stubbed responses. They prove this code handles the documented
response shape, not that Upstox actually answers that way for your account. The gap between
those two only closes by placing a real order — and the cheapest way to find out is one share
you chose, not a strategy entry you did not.

    .venv\\Scripts\\python scripts\\verify_live_order.py --symbol IDEA --quantity 1

What it does, in order:
  1. reads your funds
  2. buys `quantity` at market, and reports the price Upstox says you got
  3. prints the raw order-details response, so any field-name mismatch is visible
  4. parks a stop-loss order well below the market, then cancels it
  5. sells the position back

This spends real money: the round trip costs brokerage plus the spread. Run it during market
hours on a liquid, cheap symbol. It refuses to run without the same LIVE_TRADING_CONFIRMED
flag the bot requires, and it will not place anything until you type the confirmation.
"""

from __future__ import annotations

import argparse
import json

from algosathi.auth.upstox_auth import get_valid_token
from algosathi.config import get_settings
from algosathi.core.enums import OrderType, Side
from algosathi.core.models import OrderRequest
from algosathi.broker.upstox_broker import UpstoxBroker


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify the live Upstox order path")
    parser.add_argument("--symbol", required=True, help="a liquid, cheap symbol keeps the test cheap")
    parser.add_argument("--exchange", default="NSE_EQ")
    parser.add_argument("--quantity", type=int, default=1)
    parser.add_argument("--product", default="D", help="D delivery, I intraday")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.secrets.live_trading_confirmed:
        raise SystemExit(
            "LIVE_TRADING_CONFIRMED is not set to true in .env. This script places a real "
            "order, so it requires the same confirmation the live bot does."
        )

    broker = UpstoxBroker(
        access_token=get_valid_token(settings),
        exchange=args.exchange,
        product=args.product,
    )

    print(f"Available margin: {broker.get_funds():,.2f}")
    print(
        f"\nAbout to BUY {args.quantity} {args.symbol} at MARKET on {args.exchange}, then sell it "
        f"straight back. This is real money."
    )
    if input("Type 'yes' to continue: ").strip().lower() != "yes":
        raise SystemExit("Cancelled — nothing was placed.")

    fill = broker.place_order(
        OrderRequest(symbol=args.symbol, side=Side.BUY, quantity=args.quantity)
    )
    print(f"\nBUY filled: {fill.quantity} @ {fill.price:.2f} (order {fill.order_id})")
    print("Raw order details Upstox returned:")
    print(json.dumps(broker.get_order(fill.order_id), indent=2, default=str))

    # A stop far below the market will not trigger; this only proves it is accepted and can be
    # pulled again, which is what the live loop does on every entry and exit.
    stop_price = round(fill.price * 0.8, 2)
    print(f"\nParking a stop-loss order at {stop_price} (20% below, will not trigger)...")
    stop_id = broker.place_resting_order(
        OrderRequest(
            symbol=args.symbol,
            side=Side.SELL,
            quantity=fill.quantity,
            order_type=OrderType.SL_M,
            trigger_price=stop_price,
        )
    )
    print(f"  accepted as order {stop_id}")
    print(f"  status: {broker.get_order(stop_id).get('status')!r} (expect 'trigger pending')")
    print(f"  cancelled: {broker.cancel_order(stop_id)}")

    print(f"\nSelling {fill.quantity} {args.symbol} back...")
    exit_fill = broker.place_order(
        OrderRequest(symbol=args.symbol, side=Side.SELL, quantity=fill.quantity)
    )
    print(f"SELL filled: {exit_fill.quantity} @ {exit_fill.price:.2f}")

    gross = (exit_fill.price - fill.price) * fill.quantity
    print(f"\nRound trip P&L before charges: {gross:+.2f}")
    print(f"Position now: {broker.get_position(args.symbol)}")
    print(
        "\nIf every step above printed a real price and the stop showed 'trigger pending', the "
        "live order path works. If anything printed 0.00 or raised, stop and fix it before "
        "running the bot in live mode."
    )


if __name__ == "__main__":
    main()
