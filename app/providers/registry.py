from __future__ import annotations

from app.config import Settings
from app.providers.base import MarketProvider
from app.providers.binance_provider import BinanceProvider
from app.providers.ctrader_provider import CTraderProvider
from app.providers.paper_provider import PaperProvider


def build_provider(name: str, settings: Settings) -> MarketProvider:
    normalized = name.lower()
    if normalized == "ctrader":
        return CTraderProvider(settings)
    if normalized == "binance":
        return BinanceProvider(settings)
    return PaperProvider(settings)


def build_providers(settings: Settings) -> list[MarketProvider]:
    return [PaperProvider(settings), BinanceProvider(settings), CTraderProvider(settings)]
