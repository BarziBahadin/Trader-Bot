from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Signal, Trade
from app.exchange.base import ExchangeClient
from app.notifications.telegram import TelegramNotifier
from app.risk.risk_manager import RiskManager
from app.services.execution_guard import ExecutionBlocked, assert_order_execution_allowed
from app.strategy.rsi_ma_strategy import StrategyDecision
from app.strategy.signals import TradeSignal


class OrderManager:
    def __init__(self, settings: Settings, exchange: ExchangeClient, notifier: TelegramNotifier):
        self.settings = settings
        self.exchange = exchange
        self.notifier = notifier
        self.risk = RiskManager(settings)

    def record_signal(self, db: Session, decision: StrategyDecision) -> Signal:
        signal = Signal(
            symbol=self.settings.symbol,
            provider=getattr(self.settings, "provider", "paper"),
            asset_class=getattr(self.settings, "asset_class", "crypto"),
            timeframe=self.settings.timeframe,
            signal=decision.signal.value,
            rsi=decision.rsi,
            fast_ma=decision.fast_ma,
            slow_ma=decision.slow_ma,
            price=decision.price,
            reason=decision.reason,
        )
        db.add(signal)
        db.commit()
        db.refresh(signal)
        return signal

    def handle_decision(self, db: Session, decision: StrategyDecision) -> Trade | None:
        self.record_signal(db, decision)
        if decision.signal == TradeSignal.BUY:
            return self._buy(db, decision)
        if decision.signal == TradeSignal.SELL:
            return self._sell(db, decision)
        return None

    def _buy(self, db: Session, decision: StrategyDecision) -> Trade | None:
        balance = self._usdt_balance()
        risk = self.risk.validate_entry(db, self.settings.symbol, decision.price, balance)
        if not risk.allowed:
            self.notifier.send(f"Trade rejected: {risk.reason}")
            return None

        try:
            assert_order_execution_allowed(self.settings, getattr(self.settings, "provider", "paper"), self.settings.symbol)
            order = self.exchange.create_market_buy_order(self.settings.symbol, risk.quantity)
        except ExecutionBlocked as exc:
            self.notifier.send(f"Trade rejected: {exc}")
            return None
        trade = Trade(
            symbol=self.settings.symbol,
            provider=getattr(self.settings, "provider", "paper"),
            asset_class=getattr(self.settings, "asset_class", "crypto"),
            side="buy",
            entry_price=float(order.get("price") or decision.price),
            quantity=risk.quantity,
            lot_size=risk.quantity,
            leverage=getattr(self.settings, "default_leverage", 1.0),
            margin_required=(risk.quantity * float(order.get("price") or decision.price)) / getattr(self.settings, "default_leverage", 1.0),
            contract_size=1.0,
            stop_loss=risk.stop_loss,
            take_profit=risk.take_profit,
            pnl=0.0,
            status="open",
            mode=self.settings.bot_mode,
            reason=decision.reason,
        )
        db.add(trade)
        db.commit()
        db.refresh(trade)
        self.notifier.send(f"Order executed: BUY {risk.quantity:.8f} {self.settings.symbol}")
        return trade

    def _sell(self, db: Session, decision: StrategyDecision) -> Trade | None:
        trade = db.query(Trade).filter(Trade.symbol == self.settings.symbol, Trade.status == "open").first()
        if not trade:
            return None
        try:
            assert_order_execution_allowed(self.settings, trade.provider, trade.symbol)
            self.exchange.create_market_sell_order(self.settings.symbol, trade.quantity)
        except ExecutionBlocked as exc:
            self.notifier.send(f"Trade rejected: {exc}")
            return None
        trade.exit_price = decision.price
        trade.pnl = (decision.price - trade.entry_price) * trade.quantity
        trade.status = "closed"
        trade.closed_at = datetime.now(timezone.utc)
        trade.reason = decision.reason
        db.commit()
        db.refresh(trade)
        self.notifier.send(f"Order executed: SELL {trade.quantity:.8f} {self.settings.symbol}; PnL {trade.pnl:.2f}")
        return trade

    def _usdt_balance(self) -> float:
        balance = self.exchange.fetch_balance()
        return float(balance.get("free", {}).get("USDT") or balance.get("total", {}).get("USDT") or 0.0)
