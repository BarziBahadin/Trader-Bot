from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.db.database import Base
from app.db.models import Trade
from app.risk.risk_manager import RiskManager


def make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_live_trading_is_blocked_without_explicit_enable(tmp_path: Path):
    db = make_db()
    settings = Settings(BOT_MODE="live", ENABLE_REAL_TRADING=False, STOP_FILE=tmp_path / "STOP_BOT.txt")

    decision = RiskManager(settings).validate_entry(db, "BTC/USDT", price=50_000, balance=10_000)

    assert decision.allowed is False
    assert "ENABLE_REAL_TRADING=true" in decision.reason


def test_emergency_stop_blocks_entries(tmp_path: Path):
    db = make_db()
    stop_file = tmp_path / "STOP_BOT.txt"
    stop_file.write_text("stop", encoding="utf-8")
    settings = Settings(STOP_FILE=stop_file)

    decision = RiskManager(settings).validate_entry(db, "BTC/USDT", price=50_000, balance=10_000)

    assert decision.allowed is False
    assert "STOP_BOT.txt" in decision.reason


def test_open_position_blocks_second_entry(tmp_path: Path):
    db = make_db()
    settings = Settings(STOP_FILE=tmp_path / "STOP_BOT.txt")
    db.add(
        Trade(
            symbol="BTC/USDT",
            side="buy",
            entry_price=50_000,
            quantity=0.01,
            pnl=0,
            status="open",
            mode="paper",
        )
    )
    db.commit()

    decision = RiskManager(settings).validate_entry(db, "BTC/USDT", price=50_000, balance=10_000)

    assert decision.allowed is False
    assert "open BTC/USDT position" in decision.reason

