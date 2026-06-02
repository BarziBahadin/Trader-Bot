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

    assert "Active symbol set to XAUUSD" in reply


def test_status_command_includes_market_fields(tmp_path: Path):
    settings = Settings(STOP_FILE=tmp_path / "STOP_BOT.txt")
    db = make_db(settings)

    reply = handle_telegram_command("/status", db, settings)

    assert "Symbol:" in reply
    assert "Leverage:" in reply
