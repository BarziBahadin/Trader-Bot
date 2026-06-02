from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db.models import ConfirmationCode


def create_confirmation(db: Session, action: str, payload: dict, ttl_seconds: int = 120) -> ConfirmationCode:
    code = secrets.token_hex(3).upper()
    confirmation = ConfirmationCode(
        code=code,
        action=action,
        payload=json.dumps(payload),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
    )
    db.add(confirmation)
    db.commit()
    db.refresh(confirmation)
    return confirmation


def consume_confirmation(db: Session, code: str, action: str) -> dict | None:
    confirmation = (
        db.query(ConfirmationCode)
        .filter(ConfirmationCode.code == code.strip().upper(), ConfirmationCode.action == action, ConfirmationCode.used_at.is_(None))
        .first()
    )
    if confirmation is None or confirmation.expires_at < datetime.now(timezone.utc):
        return None
    confirmation.used_at = datetime.now(timezone.utc)
    db.commit()
    return json.loads(confirmation.payload or "{}")
