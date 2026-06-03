from __future__ import annotations

import os
import threading

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.data.market_data import MarketData
from app.db.database import SessionLocal, get_db, init_db
from app.db.models import RiskEvent, Signal, Trade
from app.markets.sizing import calculate_position_size
from app.providers.registry import build_provider, build_providers
from app.risk.risk_manager import create_stop_file, remove_stop_file
from app.services.api_auth import require_api_auth
from app.services.confirmations import consume_confirmation, create_confirmation
from app.services.execution_guard import ExecutionBlocked, assert_order_execution_allowed
from app.services.live_readiness import live_readiness
from app.services.market_service import (
    find_instrument,
    list_instruments,
    list_watchlist,
    require_app_state,
    seed_market_defaults,
    set_active_symbol,
    update_state,
    upsert_instruments,
)
from app.services.trading_worker import run_trading_worker
from app.notifications.telegram_bot import run_telegram_polling

_worker_started = False
_telegram_started = False

settings_for_app = get_settings()
app = FastAPI(title="Multi-Market Trader Bot")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings_for_app.cors_origin_list,
    allow_credentials=bool(settings_for_app.api_auth_token),
    allow_methods=["*"],
    allow_headers=["*"],
)


class SettingsPatch(BaseModel):
    active_symbol: str | None = None
    timeframe: str | None = None
    risk_percent: float | None = Field(default=None, gt=0, le=5)
    stop_loss_distance: float | None = Field(default=None, gt=0)
    take_profit_distance: float | None = Field(default=None, gt=0)
    leverage: float | None = Field(default=None, gt=0)
    lot_size: float | None = Field(default=None, gt=0)


class CalcRequest(BaseModel):
    symbol: str | None = None
    risk_percent: float | None = Field(default=None, gt=0, le=5)
    stop_loss_distance: float | None = Field(default=None, gt=0)
    take_profit_distance: float | None = Field(default=None, gt=0)
    leverage: float | None = Field(default=None, gt=0)
    price: float | None = Field(default=None, gt=0)


class ConfirmRequest(BaseModel):
    code: str


class ActivateSymbolRequest(BaseModel):
    symbol: str


@app.on_event("startup")
def startup() -> None:
    global _telegram_started, _worker_started
    settings = get_settings()
    init_db()
    with SessionLocal() as db:
        seed_market_defaults(db, settings)
        if settings.load_provider_symbols_on_startup:
            for provider in build_providers(settings):
                try:
                    upsert_instruments(db, provider.instruments())
                except Exception:
                    continue
    if os.getenv("PYTEST_CURRENT_TEST"):
        return
    if settings.auto_start_worker and not _worker_started:
        _worker_started = True
        threading.Thread(target=run_trading_worker, args=(settings,), daemon=True, name="trading-worker").start()
    if settings.auto_start_telegram and not _telegram_started:
        _telegram_started = True
        threading.Thread(target=run_telegram_polling, args=(settings,), daemon=True, name="telegram-polling").start()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/status")
def api_status(settings: Settings = Depends(get_settings), db: Session = Depends(get_db), _: None = Depends(require_api_auth)) -> dict:
    state = require_app_state(db, settings)
    open_trade = db.query(Trade).filter(Trade.symbol == state.active_symbol, Trade.status == "open").first()
    provider = build_provider(state.active_provider, settings)
    provider_status = provider.status()
    latest_price = _latest_price(provider, state.active_symbol, state.timeframe)
    account = _account_summary(provider)
    return {
        "mode": settings.bot_mode,
        "real_trading_enabled": settings.enable_real_trading,
        "symbol": state.active_symbol,
        "provider": state.active_provider,
        "asset_class": state.active_asset_class,
        "timeframe": state.timeframe,
        "risk_percent": state.risk_percent,
        "lot_size": state.lot_size,
        "leverage": state.leverage,
        "emergency_stop": settings.stop_file.exists(),
        "open_position": open_trade is not None,
        "latest_price": latest_price,
        "provider_status": provider_status.__dict__,
        "account": account,
        "live_readiness": live_readiness(settings, state.active_symbol),
    }


@app.get("/api/worker")
def api_worker(settings: Settings = Depends(get_settings)) -> dict:
    return {"running": True, "loop_interval_seconds": 60, "emergency_stop": settings.stop_file.exists()}


@app.get("/api/account")
def api_account(settings: Settings = Depends(get_settings), db: Session = Depends(get_db), _: None = Depends(require_api_auth)) -> dict:
    state = require_app_state(db, settings)
    provider = build_provider(state.active_provider, settings)
    return _account_summary(provider)


@app.get("/api/live-readiness")
def api_live_readiness(settings: Settings = Depends(get_settings), db: Session = Depends(get_db), _: None = Depends(require_api_auth)) -> dict:
    state = require_app_state(db, settings)
    return live_readiness(settings, state.active_symbol)


@app.get("/api/symbols")
def api_symbols(db: Session = Depends(get_db)) -> list[dict]:
    return [instrument.to_dict() for instrument in list_instruments(db)]


@app.get("/api/watchlist")
def api_watchlist(db: Session = Depends(get_db)) -> list[dict]:
    return [{"symbol": item.symbol, "provider": item.provider, "asset_class": item.asset_class} for item in list_watchlist(db)]


@app.post("/api/symbols/activate")
def api_activate_symbol_body(request: ActivateSymbolRequest, settings: Settings = Depends(get_settings), db: Session = Depends(get_db), _: None = Depends(require_api_auth)) -> dict:
    state = set_active_symbol(db, settings, request.symbol)
    return _state_to_dict(state)


@app.post("/api/symbols/{symbol:path}/activate")
def api_activate_symbol(symbol: str, settings: Settings = Depends(get_settings), db: Session = Depends(get_db), _: None = Depends(require_api_auth)) -> dict:
    state = set_active_symbol(db, settings, symbol)
    return _state_to_dict(state)


@app.get("/api/settings")
def api_settings(settings: Settings = Depends(get_settings), db: Session = Depends(get_db), _: None = Depends(require_api_auth)) -> dict:
    return _state_to_dict(require_app_state(db, settings))


@app.patch("/api/settings")
def api_update_settings(patch: SettingsPatch, settings: Settings = Depends(get_settings), db: Session = Depends(get_db), _: None = Depends(require_api_auth)) -> dict:
    state = update_state(db, settings, patch.model_dump(exclude_none=True))
    return _state_to_dict(state)


@app.post("/api/position-size")
def api_position_size(request: CalcRequest, settings: Settings = Depends(get_settings), db: Session = Depends(get_db), _: None = Depends(require_api_auth)) -> dict:
    state = require_app_state(db, settings)
    symbol = request.symbol or state.active_symbol
    instrument = find_instrument(db, symbol)
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"unknown symbol {symbol}")
    provider = build_provider(instrument.provider, settings)
    price = request.price or _latest_price(provider, instrument.symbol, state.timeframe)
    if price is None and (settings.bot_mode != "live" or not instrument.trade_enabled):
        price = _latest_price(build_provider("paper", settings), instrument.symbol, state.timeframe)
    if not price:
        raise HTTPException(status_code=503, detail=f"price unavailable for {instrument.symbol}")
    preview = calculate_position_size(
        instrument,
        account_balance=settings.initial_balance,
        price=price,
        risk_percent=request.risk_percent or state.risk_percent,
        stop_loss_distance=request.stop_loss_distance or state.stop_loss_distance,
        take_profit_distance=request.take_profit_distance or state.take_profit_distance,
        leverage=request.leverage or state.leverage or instrument.default_leverage,
        account_currency=settings.account_currency,
    )
    return preview.to_dict()


@app.get("/api/candles")
def api_candles_query(symbol: str, timeframe: str = "15m", limit: int = 120, settings: Settings = Depends(get_settings), db: Session = Depends(get_db)) -> list[dict]:
    return _candles_for_symbol(symbol, timeframe, limit, settings, db)


@app.get("/api/candles/{symbol:path}")
def api_candles(symbol: str, timeframe: str = "15m", limit: int = 120, settings: Settings = Depends(get_settings), db: Session = Depends(get_db)) -> list[dict]:
    return _candles_for_symbol(symbol, timeframe, limit, settings, db)


def _candles_for_symbol(symbol: str, timeframe: str, limit: int, settings: Settings, db: Session) -> list[dict]:
    instrument = find_instrument(db, symbol)
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"unknown symbol {symbol}")
    provider = build_provider(instrument.provider, settings)
    try:
        data = MarketData(provider).candles(instrument.symbol, timeframe, limit)
    except Exception:
        if settings.bot_mode == "live" and instrument.trade_enabled:
            raise HTTPException(status_code=503, detail=f"{instrument.provider} market data unavailable")
        data = MarketData(build_provider("paper", settings)).candles(instrument.symbol, timeframe, limit)
    if "timestamp" in data:
        data["timestamp"] = data["timestamp"].astype(str)
    return data.tail(limit).to_dict(orient="records")


@app.get("/api/trades")
def api_trades(db: Session = Depends(get_db), _: None = Depends(require_api_auth)) -> list[dict]:
    return [_trade_to_dict(row) for row in db.query(Trade).order_by(Trade.id.desc()).limit(200).all()]


@app.get("/api/signals")
def api_signals(db: Session = Depends(get_db), _: None = Depends(require_api_auth)) -> list[dict]:
    return [_signal_to_dict(row) for row in db.query(Signal).order_by(Signal.id.desc()).limit(200).all()]


@app.get("/api/risk-events")
def api_risk_events(db: Session = Depends(get_db), _: None = Depends(require_api_auth)) -> list[dict]:
    return [_risk_event_to_dict(row) for row in db.query(RiskEvent).order_by(RiskEvent.id.desc()).limit(200).all()]


@app.post("/api/emergency-stop")
def api_emergency_stop(settings: Settings = Depends(get_settings), _: None = Depends(require_api_auth)) -> dict:
    create_stop_file(settings.stop_file)
    return {"emergency_stop": True}


@app.post("/api/resume")
def api_resume(settings: Settings = Depends(get_settings), _: None = Depends(require_api_auth)) -> dict:
    remove_stop_file(settings.stop_file)
    return {"emergency_stop": False}


@app.post("/api/position/close/preview")
def api_close_preview(settings: Settings = Depends(get_settings), db: Session = Depends(get_db), _: None = Depends(require_api_auth)) -> dict:
    state = require_app_state(db, settings)
    trade = db.query(Trade).filter(Trade.symbol == state.active_symbol, Trade.status == "open").first()
    if trade is None:
        raise HTTPException(status_code=404, detail="no open position")
    confirmation = create_confirmation(db, "close_position", {"trade_id": trade.id, "symbol": trade.symbol, "quantity": trade.quantity})
    return {"code": confirmation.code, "expires_at": confirmation.expires_at, "trade": _trade_to_dict(trade)}


@app.post("/api/position/close/confirm")
def api_close_confirm(request: ConfirmRequest, settings: Settings = Depends(get_settings), db: Session = Depends(get_db), _: None = Depends(require_api_auth)) -> dict:
    payload = consume_confirmation(db, request.code, "close_position")
    if payload is None:
        raise HTTPException(status_code=400, detail="invalid or expired confirmation code")
    trade = db.query(Trade).filter(Trade.id == payload["trade_id"], Trade.status == "open").first()
    if trade is None:
        raise HTTPException(status_code=404, detail="open trade not found")
    try:
        assert_order_execution_allowed(settings, trade.provider, trade.symbol)
    except ExecutionBlocked as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    provider = build_provider(trade.provider, settings)
    provider.close_position(trade.symbol, trade.quantity)
    trade.status = "closed"
    trade.exit_price = _latest_price(provider, trade.symbol, require_app_state(db, settings).timeframe) or trade.entry_price
    trade.pnl = (trade.exit_price - trade.entry_price) * trade.quantity
    db.commit()
    db.refresh(trade)
    return _trade_to_dict(trade)


@app.get("/status")
def status(settings: Settings = Depends(get_settings), db: Session = Depends(get_db)) -> dict:
    return api_status(settings, db)


@app.get("/trades")
def trades(db: Session = Depends(get_db)) -> list[dict]:
    return api_trades(db)


@app.get("/signals")
def signals(db: Session = Depends(get_db)) -> list[dict]:
    return api_signals(db)


@app.get("/risk-events")
def risk_events(db: Session = Depends(get_db)) -> list[dict]:
    return api_risk_events(db)


@app.post("/emergency-stop")
def emergency_stop(settings: Settings = Depends(get_settings)) -> dict:
    return api_emergency_stop(settings)


@app.post("/resume")
def resume(settings: Settings = Depends(get_settings)) -> dict:
    return api_resume(settings)


def _latest_price(provider, symbol: str, timeframe: str) -> float | None:
    try:
        candles = provider.fetch_ohlcv(symbol, timeframe, 2)
    except Exception:
        return None
    if not candles:
        return None
    return float(candles[-1][4])


def _account_summary(provider) -> dict:
    if hasattr(provider, "account_summary"):
        try:
            return provider.account_summary()
        except Exception as exc:
            return {"connected": False, "message": _safe_error_message(exc)}
    try:
        balance = provider.fetch_balance()
    except Exception as exc:
        return {"connected": False, "message": _safe_error_message(exc)}
    return {
        "connected": True,
        "currency": "USDT",
        "equity": float((balance.get("total") or {}).get("USDT") or 0.0),
        "free": float((balance.get("free") or {}).get("USDT") or 0.0),
        "used": float((balance.get("used") or {}).get("USDT") or 0.0),
        "total": float((balance.get("total") or {}).get("USDT") or 0.0),
        "unrealized_pnl": 0.0,
        "message": "balance loaded",
    }


def _safe_error_message(exc: Exception) -> str:
    return exc.__class__.__name__


def _state_to_dict(state) -> dict:
    return {
        "active_symbol": state.active_symbol,
        "active_provider": state.active_provider,
        "active_asset_class": state.active_asset_class,
        "timeframe": state.timeframe,
        "risk_percent": state.risk_percent,
        "stop_loss_distance": state.stop_loss_distance,
        "take_profit_distance": state.take_profit_distance,
        "leverage": state.leverage,
        "lot_size": state.lot_size,
        "updated_at": state.updated_at,
    }


def _trade_to_dict(trade: Trade) -> dict:
    return {
        "id": trade.id,
        "symbol": trade.symbol,
        "provider": trade.provider,
        "asset_class": trade.asset_class,
        "side": trade.side,
        "entry_price": trade.entry_price,
        "exit_price": trade.exit_price,
        "quantity": trade.quantity,
        "lot_size": trade.lot_size,
        "leverage": trade.leverage,
        "margin_required": trade.margin_required,
        "contract_size": trade.contract_size,
        "stop_loss": trade.stop_loss,
        "take_profit": trade.take_profit,
        "pnl": trade.pnl,
        "status": trade.status,
        "mode": trade.mode,
        "opened_at": trade.opened_at,
        "closed_at": trade.closed_at,
        "reason": trade.reason,
    }


def _signal_to_dict(signal: Signal) -> dict:
    return {
        "id": signal.id,
        "symbol": signal.symbol,
        "provider": signal.provider,
        "asset_class": signal.asset_class,
        "timeframe": signal.timeframe,
        "signal": signal.signal,
        "rsi": signal.rsi,
        "fast_ma": signal.fast_ma,
        "slow_ma": signal.slow_ma,
        "price": signal.price,
        "reason": signal.reason,
        "created_at": signal.created_at,
    }


def _risk_event_to_dict(event: RiskEvent) -> dict:
    return {"id": event.id, "event_type": event.event_type, "message": event.message, "created_at": event.created_at}
