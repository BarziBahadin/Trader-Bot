from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.config import Settings
from app.strategy.indicators import add_indicators
from app.strategy.signals import TradeSignal


@dataclass(frozen=True)
class StrategyDecision:
    signal: TradeSignal
    reason: str
    price: float
    rsi: float | None
    fast_ma: float | None
    slow_ma: float | None


class RsiMaStrategy:
    def __init__(self, settings: Settings):
        self.settings = settings

    def evaluate(
        self,
        candles: pd.DataFrame,
        has_open_position: bool,
        entry_price: float | None = None,
    ) -> StrategyDecision:
        if candles.empty or len(candles) < self.settings.slow_ma:
            return StrategyDecision(TradeSignal.HOLD, "not enough candles", 0.0, None, None, None)

        enriched = add_indicators(
            candles,
            self.settings.rsi_period,
            self.settings.fast_ma,
            self.settings.slow_ma,
        )
        latest = enriched.iloc[-1]
        price = float(latest["close"])
        rsi_value = _optional_float(latest["rsi"])
        fast_ma = _optional_float(latest["fast_ma"])
        slow_ma = _optional_float(latest["slow_ma"])

        if rsi_value is None or fast_ma is None or slow_ma is None:
            return StrategyDecision(TradeSignal.HOLD, "indicators not ready", price, rsi_value, fast_ma, slow_ma)

        if has_open_position and entry_price:
            if price <= entry_price * (1 - self.settings.stop_loss_percent):
                return StrategyDecision(TradeSignal.SELL, "stop-loss hit", price, rsi_value, fast_ma, slow_ma)
            if price >= entry_price * (1 + self.settings.take_profit_percent):
                return StrategyDecision(TradeSignal.SELL, "take-profit hit", price, rsi_value, fast_ma, slow_ma)
            if rsi_value > self.settings.rsi_sell_level:
                return StrategyDecision(TradeSignal.SELL, "RSI sell level", price, rsi_value, fast_ma, slow_ma)
            if fast_ma < slow_ma:
                return StrategyDecision(TradeSignal.SELL, "fast MA below slow MA", price, rsi_value, fast_ma, slow_ma)

        if not has_open_position and rsi_value < self.settings.rsi_buy_level and fast_ma > slow_ma:
            return StrategyDecision(TradeSignal.BUY, "RSI buy level and bullish MA", price, rsi_value, fast_ma, slow_ma)

        return StrategyDecision(TradeSignal.HOLD, "no setup", price, rsi_value, fast_ma, slow_ma)


def _optional_float(value) -> float | None:
    if pd.isna(value):
        return None
    return float(value)
