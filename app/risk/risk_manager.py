from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import RiskEvent, Trade
from app.services.execution_guard import ExecutionBlocked, assert_order_execution_allowed


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
        if self._has_open_position(db, symbol):
            return self._reject(db, "open_position_exists", f"open {symbol} position already exists")
        provider_name = getattr(self.settings, "provider", "paper")
        if self.settings.bot_mode == "live" or provider_name != "paper":
            try:
                assert_order_execution_allowed(self.settings, provider_name, symbol)
            except ExecutionBlocked as exc:
                return self._reject(db, "real_trading_blocked", str(exc))
        if self.settings.bot_mode == "backtest":
            return self._reject(db, "backtest_execution_blocked", "backtest mode cannot place live orders")
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
            notional = quantity * price
        if provider_name != "paper" and notional > self.settings.max_position_notional:
            quantity = self.settings.max_position_notional / price
            notional = quantity * price
        if quantity <= 0:
            return self._reject(db, "minimum_balance", "balance too low for order")

        return RiskDecision(True, "allowed", quantity, stop_loss, take_profit)

    def _validate_live_futures(self, symbol: str) -> str | None:
        if not self.settings.enable_real_trading:
            return "live mode requires ENABLE_REAL_TRADING=true"
        if not self.settings.api_auth_token:
            return "live futures requires API_AUTH_TOKEN"
        if self.settings.live_trading_ack != "I_UNDERSTAND_LIVE_FUTURES_RISK":
            return "live futures requires LIVE_TRADING_ACK=I_UNDERSTAND_LIVE_FUTURES_RISK"
        if self.settings.provider != "okx":
            return "live futures requires PROVIDER=okx"
        if self.settings.okx_demo:
            return "live futures requires OKX_DEMO=false"
        if self.settings.okx_market_type not in {"swap", "future", "futures"}:
            return "live futures requires OKX_MARKET_TYPE=swap"
        if not (self.settings.okx_api_key and self.settings.okx_api_secret and self.settings.okx_passphrase):
            return "live futures requires OKX_API_KEY, OKX_API_SECRET, and OKX_PASSPHRASE"
        if self.settings.default_leverage > self.settings.max_leverage:
            return f"DEFAULT_LEVERAGE cannot exceed MAX_LEVERAGE={self.settings.max_leverage}"
        if ":USDT" not in symbol:
            return "live futures requires an OKX swap symbol such as BTC/USDT:USDT"
        return None

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
