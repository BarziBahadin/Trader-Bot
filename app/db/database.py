from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_sqlite()


def _migrate_sqlite() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    additions = {
        "trades": {
            "provider": "VARCHAR(32) DEFAULT 'paper'",
            "asset_class": "VARCHAR(32) DEFAULT 'crypto'",
            "lot_size": "FLOAT",
            "leverage": "FLOAT",
            "margin_required": "FLOAT",
            "contract_size": "FLOAT",
            "stop_loss": "FLOAT",
            "take_profit": "FLOAT",
        },
        "signals": {
            "provider": "VARCHAR(32) DEFAULT 'paper'",
            "asset_class": "VARCHAR(32) DEFAULT 'crypto'",
            "reason": "TEXT DEFAULT ''",
        },
        "confirmation_codes": {
            "code_hash": "VARCHAR(128)",
            "requester_id": "VARCHAR(64)",
        },
    }
    with engine.begin() as connection:
        for table, columns in additions.items():
            existing = {row[1] for row in connection.execute(text(f"PRAGMA table_info({table})"))}
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
