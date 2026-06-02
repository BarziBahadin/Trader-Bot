from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.db.database import Base
from app.main import ActivateSymbolRequest, app, api_activate_symbol_body, api_candles_query, api_position_size, CalcRequest
from app.services.market_service import seed_market_defaults


def make_db(settings):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    seed_market_defaults(db, settings)
    return db


def test_crypto_symbol_with_slash_route_uses_path_converter():
    route_paths = {getattr(route, "path", "") for route in app.routes}

    assert "/api/candles/{symbol:path}" in route_paths
    assert "/api/symbols/{symbol:path}/activate" in route_paths


def test_query_candles_endpoint_accepts_slash_symbol_with_price_override_style(tmp_path: Path):
    settings = Settings(STOP_FILE=tmp_path / "STOP_BOT.txt")
    db = make_db(settings)

    state = api_activate_symbol_body(ActivateSymbolRequest(symbol="XAUUSD"), settings, db)

    assert state["active_symbol"] == "XAUUSD"
    candles = api_candles_query("XAUUSD", "15m", 5, settings, db)
    assert len(candles) == 5


def test_crypto_symbol_with_slash_can_preview_position_size(tmp_path: Path):
    settings = Settings(STOP_FILE=tmp_path / "STOP_BOT.txt")
    db = make_db(settings)

    preview = api_position_size(CalcRequest(symbol="BTC/USDT", price=50_000), settings, db)

    assert preview["symbol"] == "BTC/USDT"
