from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import RiskEvent, Trade


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str
    quantity: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0


class RiskManager:
    def __init__(self, settings: Settings):
        self.settings = settings

    def validate_entry(self, db: Session, symbol: str, price: float, balance: float) -> RiskDecision:
        if self.settings.stop_file.exists():
            return self._reject(db, "emergency_stop", "STOP_BOT.txt exists")
        if self.settings.bot_mode == "live" and not self.settings.enable_real_trading:
            return self._reject(db, "real_trading_blocked", "live mode requires ENABLE_REAL_TRADING=true")
        if self.settings.bot_mode == "backtest":
            return self._reject(db, "backtest_execution_blocked", "backtest mode cannot place live orders")
        if self._has_open_position(db, symbol):
            return self._reject(db, "open_position_exists", f"open {symbol} position already exists")
        if price <= 0:
            return self._reject(db, "invalid_price", "order price must be positive")
        if balance <= 0:
            return self._reject(db, "minimum_balance", "balance must be positive")
        if self._daily_loss(db) <= -(balance * self.settings.max_daily_loss):
            return self._reject(db, "daily_loss_limit", "daily max loss reached")

        stop_loss = price * (1 - self.settings.stop_loss_percent)
        take_profit = price * (1 + self.settings.take_profit_percent)
        risk_amount = balance * self.settings.risk_per_trade
        unit_risk = price - stop_loss
        quantity = risk_amount / unit_risk
        notional = quantity * price

        if stop_loss <= 0:
            return self._reject(db, "missing_stop_loss", "stop-loss is required")
        if notional > balance:
            quantity = balance / price
        if quantity <= 0:
            return self._reject(db, "minimum_balance", "balance too low for order")

        return RiskDecision(True, "allowed", quantity, stop_loss, take_profit)

    def _has_open_position(self, db: Session, symbol: str) -> bool:
        return db.query(Trade).filter(Trade.symbol == symbol, Trade.status == "open").first() is not None

    def _daily_loss(self, db: Session) -> float:
        today = datetime.now(timezone.utc).date()
        start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
        return float(
            db.query(func.coalesce(func.sum(Trade.pnl), 0.0))
            .filter(Trade.closed_at >= start)
            .scalar()
            or 0.0
        )

    def _reject(self, db: Session, event_type: str, message: str) -> RiskDecision:
        db.add(RiskEvent(event_type=event_type, message=message))
        db.commit()
        return RiskDecision(False, message)


def create_stop_file(path: Path) -> None:
    path.write_text("Emergency stop enabled.\n", encoding="utf-8")


def remove_stop_file(path: Path) -> None:
    if path.exists():
        path.unlink()

