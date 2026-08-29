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
