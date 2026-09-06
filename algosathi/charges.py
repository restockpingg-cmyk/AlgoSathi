"""What a trade actually costs in India, so paper results are not quietly optimistic.

A paper broker that fills instantly at the quoted price with no charges will show a profit
that the same trades would not have made live. That matters here more than usual: the edge
measured on INFY was about 3.4 points per round trip on a ~1,050 rupee stock, roughly 0.3%,
and charges plus slippage on an equity round trip land in the same range. The difference
between "small edge" and "no edge" is entirely inside the costs.

Rates differ by broker and change over time, so every one is configurable and the defaults
below are ballpark figures for Indian equity delivery. Check them against your own broker's
brokerage calculator before trusting a number this produces.
"""

from __future__ import annotations

from dataclasses import dataclass

from algosathi.config import ChargesConfig
from algosathi.core.enums import Side


@dataclass(frozen=True)
class Charges:
    """Rupee cost of one leg, broken out so the dashboard can explain a number rather than
    just assert it."""

    brokerage: float
    stt: float
    exchange: float
    sebi: float
    stamp_duty: float
    gst: float

    @property
    def total(self) -> float:
        return self.brokerage + self.stt + self.exchange + self.sebi + self.stamp_duty + self.gst


def charges_for(config: ChargesConfig, side: Side, price: float, quantity: int) -> Charges:
    """Charges on a single leg of `quantity` at `price`."""
    turnover = price * quantity
    if turnover <= 0:
        return Charges(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    # Indian brokers bill the lower of a flat fee and a percentage of turnover.
    percentage_fee = turnover * config.brokerage_pct / 100
    brokerage = min(config.brokerage_flat, percentage_fee) if config.brokerage_flat else percentage_fee

    stt_pct = config.stt_pct_sell if side is Side.SELL else config.stt_pct_buy
    stt = turnover * stt_pct / 100

    exchange = turnover * config.exchange_pct / 100
    sebi = turnover * config.sebi_pct / 100
    # Stamp duty is charged on the buy leg only.
    stamp_duty = turnover * config.stamp_duty_pct_buy / 100 if side is Side.BUY else 0.0

    # GST applies to brokerage and the exchange/SEBI fees, not to STT or stamp duty.
    gst = (brokerage + exchange + sebi) * config.gst_pct / 100

    return Charges(
        brokerage=brokerage,
        stt=stt,
        exchange=exchange,
        sebi=sebi,
        stamp_duty=stamp_duty,
        gst=gst,
    )


def slipped_price(config: ChargesConfig, side: Side, price: float) -> float:
    """The price you actually get, rather than the one you saw.

    Slippage always works against you: a buy fills a little higher than quoted, a sell a
    little lower. It is not a charge on the bill — it is a worse fill — so it is modelled
    here as a price adjustment and reported separately from the charges.
    """
    drift = price * config.slippage_pct / 100
    return price + drift if side is Side.BUY else price - drift
