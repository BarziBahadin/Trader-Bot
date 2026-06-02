from typing import Any

import ccxt

from app.config import Settings
from app.exchange.base import ExchangeClient


class BinanceClient(ExchangeClient):
    def __init__(self, settings: Settings):
        if settings.bot_mode == "live" and not settings.enable_real_trading:
            raise RuntimeError("Live trading is blocked unless ENABLE_REAL_TRADING=true")

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

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 200) -> list[list[float]]:
        return self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    def fetch_balance(self) -> dict[str, Any]:
        return self.exchange.fetch_balance()

    def create_market_buy_order(self, symbol: str, amount: float) -> dict[str, Any]:
        return self.exchange.create_market_buy_order(symbol, amount)

    def create_market_sell_order(self, symbol: str, amount: float) -> dict[str, Any]:
        return self.exchange.create_market_sell_order(symbol, amount)

