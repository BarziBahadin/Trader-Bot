from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.db.database import Base
from app.notifications.telegram_commands import handle_telegram_command
from app.services.market_service import seed_market_defaults


def make_db(settings):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    seed_market_defaults(db, settings)
    return db


def test_set_symbol_command(tmp_path: Path):
    settings = Settings(STOP_FILE=tmp_path / "STOP_BOT.txt")
    db = make_db(settings)

    reply = handle_telegram_command("/set XAUUSD", db, settings)

    assert "Active market changed to XAUUSD" in reply


def test_status_command_includes_market_fields(tmp_path: Path):
    settings = Settings(STOP_FILE=tmp_path / "STOP_BOT.txt")
    db = make_db(settings)

    reply = handle_telegram_command("/status", db, settings)

    assert "Market:" in reply
    assert "Leverage:" in reply


def test_start_command_shows_friendly_menu(tmp_path: Path):
    settings = Settings(STOP_FILE=tmp_path / "STOP_BOT.txt")
    db = make_db(settings)

    reply = handle_telegram_command("/start", db, settings)

    assert "Trader bot menu" in reply
    assert "/setrisk" in reply


def test_plain_status_alias_works(tmp_path: Path):
    settings = Settings(STOP_FILE=tmp_path / "STOP_BOT.txt")
    db = make_db(settings)

    reply = handle_telegram_command("status", db, settings)

    assert "Bot status" in reply


def test_setrisk_updates_risk_settings(tmp_path: Path):
    settings = Settings(STOP_FILE=tmp_path / "STOP_BOT.txt", MAX_LEVERAGE=3)
    db = make_db(settings)

    reply = handle_telegram_command("/setrisk 1 50 100 2", db, settings)

    assert "Risk updated" in reply
    assert "Leverage: 2.0x" in reply


def test_calc_bad_numbers_returns_helpful_reply(tmp_path: Path):
    settings = Settings(STOP_FILE=tmp_path / "STOP_BOT.txt")
    db = make_db(settings)

    reply = handle_telegram_command("/calc BTC/USDT nope 50", db, settings)

    assert "Example" in reply
