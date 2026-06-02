from enum import Enum


class TradeSignal(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
