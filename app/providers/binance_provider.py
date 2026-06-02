from __future__ import annotations

from typing import Any

import ccxt

from app.config import Settings
from app.markets.instruments import DEFAULT_INSTRUMENTS, Instrument
from app.providers.base import MarketProvider, ProviderStatus


class BinanceProvider(MarketProvider):
    name = "binance"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.exchange = ccxt.binance(
            {
                "apiKey": settings.binance_api_key,
                "secret": settings.binance_api_secret,
                "enableRateLimit": True,
            }
        )
        if settings.bot_mode == "testnet" or settings.binance_testnet:
            self.exchange.set_sandbox_mode(True)

    def status(self) -> ProviderStatus:
        return ProviderStatus(self.name, True, "Binance provider initialized")

    def instruments(self) -> list[Instrument]:
        return [instrument for instrument in DEFAULT_INSTRUMENTS if instrument.provider == "binance"]

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 200) -> list[list[float]]:
        return self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    def fetch_balance(self) -> dict[str, Any]:
        return self.exchange.fetch_balance()

    def close_position(self, symbol: str, quantity: float) -> dict[str, Any]:
        return self.exchange.create_market_sell_order(symbol, quantity)

    def create_market_buy_order(self, symbol: str, amount: float) -> dict[str, Any]:
        return self.exchange.create_market_buy_order(symbol, amount)

    def create_market_sell_order(self, symbol: str, amount: float) -> dict[str, Any]:
        return self.exchange.create_market_sell_order(symbol, amount)
