from dataclasses import dataclass

import pandas as pd

from app.config import Settings
from app.strategy.rsi_ma_strategy import RsiMaStrategy
from app.strategy.signals import TradeSignal


@dataclass
class BacktestResult:
    trades: list[dict]
    final_balance: float
    total_pnl: float


class Backtester:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.strategy = RsiMaStrategy(settings)

    def run(self, candles: pd.DataFrame) -> BacktestResult:
        balance = self.settings.initial_balance
        position_qty = 0.0
        entry_price = None
        trades: list[dict] = []

        for idx in range(self.settings.slow_ma, len(candles) + 1):
            window = candles.iloc[:idx]
            decision = self.strategy.evaluate(window, position_qty > 0, entry_price)
            if decision.signal == TradeSignal.BUY and position_qty == 0:
                stop_loss = decision.price * (1 - self.settings.stop_loss_percent)
                quantity = min((balance * self.settings.risk_per_trade) / (decision.price - stop_loss), balance / decision.price)
                balance -= quantity * decision.price
                position_qty = quantity
                entry_price = decision.price
                trades.append({"side": "buy", "price": decision.price, "quantity": quantity, "reason": decision.reason})
            elif decision.signal == TradeSignal.SELL and position_qty > 0 and entry_price:
                pnl = (decision.price - entry_price) * position_qty
                balance += position_qty * decision.price
                trades.append({"side": "sell", "price": decision.price, "quantity": position_qty, "pnl": pnl, "reason": decision.reason})
                position_qty = 0.0
                entry_price = None

        if position_qty > 0 and entry_price:
            last_price = float(candles.iloc[-1]["close"])
            balance += position_qty * last_price

        total_pnl = balance - self.settings.initial_balance
        return BacktestResult(trades=trades, final_balance=balance, total_pnl=total_pnl)

