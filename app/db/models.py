from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    provider: Mapped[str] = mapped_column(String(32), default="paper", index=True)
    asset_class: Mapped[str] = mapped_column(String(32), default="crypto", index=True)
    side: Mapped[str] = mapped_column(String(8))
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quantity: Mapped[float] = mapped_column(Float)
    lot_size: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    leverage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    margin_required: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    contract_size: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), index=True)
    mode: Mapped[str] = mapped_column(String(16), index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    provider: Mapped[str] = mapped_column(String(32), default="paper", index=True)
    asset_class: Mapped[str] = mapped_column(String(32), default="crypto", index=True)
    timeframe: Mapped[str] = mapped_column(String(16))
    signal: Mapped[str] = mapped_column(String(16), index=True)
    rsi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fast_ma: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    slow_ma: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RiskEvent(Base):
    __tablename__ = "risk_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AppState(Base):
    __tablename__ = "app_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    active_symbol: Mapped[str] = mapped_column(String(32), default="BTC/USDT", index=True)
    active_provider: Mapped[str] = mapped_column(String(32), default="paper")
    active_asset_class: Mapped[str] = mapped_column(String(32), default="crypto")
    timeframe: Mapped[str] = mapped_column(String(16), default="15m")
    risk_percent: Mapped[float] = mapped_column(Float, default=1.0)
    stop_loss_distance: Mapped[float] = mapped_column(Float, default=100.0)
    take_profit_distance: Mapped[float] = mapped_column(Float, default=200.0)
    leverage: Mapped[float] = mapped_column(Float, default=1.0)
    lot_size: Mapped[float] = mapped_column(Float, default=0.01)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InstrumentModel(Base):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    asset_class: Mapped[str] = mapped_column(String(32), index=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    base_currency: Mapped[str] = mapped_column(String(16), default="")
    quote_currency: Mapped[str] = mapped_column(String(16), default="")
    digits: Mapped[int] = mapped_column(Integer, default=2)
    point: Mapped[float] = mapped_column(Float, default=0.01)
    contract_size: Mapped[float] = mapped_column(Float, default=1.0)
    volume_min: Mapped[float] = mapped_column(Float, default=0.01)
    volume_step: Mapped[float] = mapped_column(Float, default=0.01)
    default_leverage: Mapped[float] = mapped_column(Float, default=1.0)
    tick_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    spread: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    trade_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    provider: Mapped[str] = mapped_column(String(32), default="paper", index=True)
    asset_class: Mapped[str] = mapped_column(String(32), default="crypto", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConfirmationCode(Base):
    __tablename__ = "confirmation_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(16), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PaperAccount(Base):
    __tablename__ = "paper_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    cash: Mapped[float] = mapped_column(Float, default=10_000.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
