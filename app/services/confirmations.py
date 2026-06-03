from __future__ import annotations

import json
import secrets
import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db.models import ConfirmationCode


def create_confirmation(db: Session, action: str, payload: dict, ttl_seconds: int = 120, requester_id: str | None = None) -> ConfirmationCode:
    code = secrets.token_hex(3).upper()
    confirmation = ConfirmationCode(
        code="",
        code_hash=_hash_code(code),
        action=action,
        requester_id=requester_id,
        payload=json.dumps(payload),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
    )
    db.add(confirmation)
    db.commit()
    confirmation.code = code
    return confirmation


def consume_confirmation(db: Session, code: str, action: str, requester_id: str | None = None) -> dict | None:
    normalized = code.strip().upper()
    confirmation = (
        db.query(ConfirmationCode)
        .filter(ConfirmationCode.action == action, ConfirmationCode.used_at.is_(None))
        .filter((ConfirmationCode.code_hash == _hash_code(normalized)) | (ConfirmationCode.code == normalized))
        .first()
    )
    if confirmation is None or confirmation.expires_at < datetime.now(timezone.utc):
        return None
    if confirmation.requester_id and requester_id and confirmation.requester_id != requester_id:
        return None
    if confirmation.requester_id and requester_id is None:
        return None
    confirmation.used_at = datetime.now(timezone.utc)
    db.commit()
    return json.loads(confirmation.payload or "{}")


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()
