from __future__ import annotations

from app.config import Settings
from app.providers.base import MarketProvider
from app.providers.okx_provider import OkxProvider
from app.providers.paper_provider import PaperProvider


def build_provider(name: str, settings: Settings) -> MarketProvider:
    normalized = name.lower()
    if normalized == "okx":
        return OkxProvider(settings)
    return PaperProvider(settings)


def build_providers(settings: Settings) -> list[MarketProvider]:
    return [PaperProvider(settings), OkxProvider(settings)]
