from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import AppState, InstrumentModel, WatchlistItem
from app.markets.instruments import DEFAULT_INSTRUMENTS, DEFAULT_WATCHLIST_SYMBOLS, Instrument, default_instrument, normalize_symbol


OLD_REAL_PROVIDERS = {"binance", "ctrader", "mt5"}


def seed_market_defaults(db: Session, settings: Settings) -> None:
    _normalize_old_providers(db)
    _upsert_default_instruments(db)
    if db.query(WatchlistItem).first() is None:
        _seed_default_watchlist(db)
    else:
        _repair_watchlist(db)
    if get_app_state(db) is None:
        active = default_instrument(settings.symbol, settings.provider)
        db.add(
            AppState(
                id=1,
                active_symbol=settings.symbol,
                active_provider=settings.provider,
                active_asset_class=settings.asset_class or active.asset_class,
                timeframe=settings.timeframe,
                risk_percent=settings.risk_per_trade * 100,
                stop_loss_distance=100.0,
                take_profit_distance=200.0,
                leverage=settings.default_leverage,
                lot_size=settings.default_lot_size,
            )
        )
    db.commit()


def _normalize_old_providers(db: Session) -> None:
    for row in db.query(InstrumentModel).all():
        if row.provider in OLD_REAL_PROVIDERS:
            row.provider = "okx"
    for row in db.query(WatchlistItem).all():
        if row.provider in OLD_REAL_PROVIDERS:
            row.provider = "okx"
    state = get_app_state(db)
    if state and state.active_provider in OLD_REAL_PROVIDERS:
        state.active_provider = "okx"


def _upsert_default_instruments(db: Session) -> None:
    for instrument in DEFAULT_INSTRUMENTS:
        existing = _find_instrument_model(db, instrument.symbol, instrument.provider)
        if existing:
            for key, value in instrument.to_dict().items():
                setattr(existing, key, value)
        else:
            db.add(_instrument_model(instrument))


def _seed_default_watchlist(db: Session) -> None:
    for symbol in DEFAULT_WATCHLIST_SYMBOLS:
        instrument = find_instrument(db, symbol)
        if instrument:
            db.add(WatchlistItem(symbol=instrument.symbol, provider=instrument.provider, asset_class=instrument.asset_class))


def _repair_watchlist(db: Session) -> None:
    desired_symbols = {normalize_symbol(symbol) for symbol in DEFAULT_WATCHLIST_SYMBOLS}
    for item in list(db.query(WatchlistItem).all()):
        if normalize_symbol(item.symbol) not in desired_symbols:
            db.delete(item)
    existing = {(normalize_symbol(item.symbol), item.provider) for item in db.query(WatchlistItem).all()}
    for symbol in DEFAULT_WATCHLIST_SYMBOLS:
        instrument = find_instrument(db, symbol)
        if instrument and (normalize_symbol(instrument.symbol), instrument.provider) not in existing:
            db.add(WatchlistItem(symbol=instrument.symbol, provider=instrument.provider, asset_class=instrument.asset_class))
            existing.add((normalize_symbol(instrument.symbol), instrument.provider))


def get_app_state(db: Session) -> AppState | None:
    return db.query(AppState).filter(AppState.id == 1).first()


def require_app_state(db: Session, settings: Settings) -> AppState:
    state = get_app_state(db)
    if state is None:
        seed_market_defaults(db, settings)
        state = get_app_state(db)
    if state is None:
        raise RuntimeError("app state could not be initialized")
    return state


def list_instruments(db: Session) -> list[Instrument]:
    rows = db.query(InstrumentModel).order_by(InstrumentModel.asset_class, InstrumentModel.symbol).all()
    return [_instrument_from_model(row) for row in rows]


def list_watchlist(db: Session) -> list[WatchlistItem]:
    return db.query(WatchlistItem).order_by(WatchlistItem.asset_class, WatchlistItem.symbol).all()


def find_instrument(db: Session, symbol: str) -> Instrument | None:
    normalized = normalize_symbol(symbol)
    rows = db.query(InstrumentModel).all()
    for row in rows:
        if normalize_symbol(row.symbol) == normalized:
            return _instrument_from_model(row)
    return None


def _find_instrument_model(db: Session, symbol: str, provider: str) -> InstrumentModel | None:
    normalized = normalize_symbol(symbol)
    rows = db.query(InstrumentModel).filter(InstrumentModel.provider == provider).all()
    for row in rows:
        if normalize_symbol(row.symbol) == normalized:
            return row
    return None


def upsert_instruments(db: Session, instruments: list[Instrument]) -> None:
    for instrument in instruments:
        existing = find_instrument(db, instrument.symbol)
        if existing:
            db.query(InstrumentModel).filter(InstrumentModel.symbol == existing.symbol).update(instrument.to_dict())
        else:
            db.add(_instrument_model(instrument))
    db.commit()


def set_active_symbol(db: Session, settings: Settings, symbol: str) -> AppState:
    state = require_app_state(db, settings)
    instrument = find_instrument(db, symbol) or default_instrument(symbol, state.active_provider)
    state.active_symbol = instrument.symbol
    state.active_provider = instrument.provider
    state.active_asset_class = instrument.asset_class
    state.leverage = instrument.default_leverage
    state.updated_at = datetime.now(timezone.utc)
    _ensure_watchlist(db, instrument)
    db.commit()
    db.refresh(state)
    return state


def update_state(db: Session, settings: Settings, values: dict) -> AppState:
    state = require_app_state(db, settings)
    allowed = {"timeframe", "risk_percent", "stop_loss_distance", "take_profit_distance", "leverage", "lot_size"}
    for key, value in values.items():
        if key in allowed and value is not None:
            setattr(state, key, value)
    if values.get("active_symbol"):
        instrument = find_instrument(db, str(values["active_symbol"])) or default_instrument(str(values["active_symbol"]), state.active_provider)
        state.active_symbol = instrument.symbol
        state.active_provider = instrument.provider
        state.active_asset_class = instrument.asset_class
        _ensure_watchlist(db, instrument)
    state.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(state)
    return state


def _ensure_watchlist(db: Session, instrument: Instrument) -> None:
    normalized = normalize_symbol(instrument.symbol)
    exists = any(normalize_symbol(item.symbol) == normalized for item in db.query(WatchlistItem).all())
    if not exists:
        db.add(WatchlistItem(symbol=instrument.symbol, provider=instrument.provider, asset_class=instrument.asset_class))


def _instrument_model(instrument: Instrument) -> InstrumentModel:
    return InstrumentModel(**instrument.to_dict())


def _instrument_from_model(row: InstrumentModel) -> Instrument:
    return Instrument(
        symbol=row.symbol,
        display_name=row.display_name or row.symbol,
        asset_class=row.asset_class,
        provider=row.provider,
        base_currency=row.base_currency,
        quote_currency=row.quote_currency,
        digits=row.digits,
        point=row.point,
        contract_size=row.contract_size,
        volume_min=row.volume_min,
        volume_step=row.volume_step,
        default_leverage=row.default_leverage,
        tick_value=row.tick_value,
        spread=row.spread,
        trade_enabled=row.trade_enabled,
    )
