from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, Request, status

from app.config import Settings, get_settings


def require_api_auth(request: Request, settings: Settings = Depends(get_settings)) -> None:
    if not settings.api_auth_token:
        return
    supplied = request.headers.get("X-API-Key") or _bearer_token(request.headers.get("Authorization", ""))
    if not supplied or not hmac.compare_digest(supplied, settings.api_auth_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="valid API token required")


def _bearer_token(header: str) -> str:
    prefix = "Bearer "
    if header.startswith(prefix):
        return header[len(prefix) :].strip()
    return ""
