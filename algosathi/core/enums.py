from enum import Enum


class Mode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class SignalType(str, Enum):
    BUY = "buy"
    EXIT = "exit"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    # Stop orders rest at the exchange and trigger on tick rather than being polled for.
    # SL carries a limit price as well as the trigger; SL_M fills at market once triggered,
    # which is what you want for a protective stop — a limit can go unfilled in exactly the
    # fast move you needed it for.
    SL = "sl"
    SL_M = "sl_m"
