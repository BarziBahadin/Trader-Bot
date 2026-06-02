import pandas as pd

from app.config import Settings
from app.strategy.rsi_ma_strategy import RsiMaStrategy
from app.strategy.signals import TradeSignal


def test_strategy_holds_when_not_enough_candles():
    settings = Settings()
    candles = pd.DataFrame({"close": [1, 2, 3]})

    decision = RsiMaStrategy(settings).evaluate(candles, has_open_position=False)

    assert decision.signal == TradeSignal.HOLD
    assert decision.reason == "not enough candles"


def test_strategy_sells_on_stop_loss():
    settings = Settings()
    candles = pd.DataFrame({"close": [100.0] * 59 + [98.0]})

    decision = RsiMaStrategy(settings).evaluate(candles, has_open_position=True, entry_price=100.0)

    assert decision.signal == TradeSignal.SELL
    assert decision.reason == "stop-loss hit"

