from __future__ import annotations

import math
import time
from typing import Any

import ccxt

from app.config import Settings
from app.markets.instruments import DEFAULT_INSTRUMENTS, Instrument, infer_asset_class
from app.providers.base import MarketProvider, ProviderStatus


class PaperProvider(MarketProvider):
    name = "paper"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.cash = settings.initial_balance
        self.exchange = ccxt.binance({"enableRateLimit": True})

    def status(self) -> ProviderStatus:
        return ProviderStatus(self.name, True, "Paper provider active")

    def instruments(self) -> list[Instrument]:
        return [Instrument(**{**instrument.to_dict(), "provider": "paper"}) for instrument in DEFAULT_INSTRUMENTS]

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 200) -> list[list[float]]:
        if infer_asset_class(symbol) == "crypto":
            crypto_symbol = symbol if "/" in symbol else symbol.replace("USDT", "/USDT")
            return self.exchange.fetch_ohlcv(crypto_symbol, timeframe=timeframe, limit=limit)
        return _synthetic_ohlcv(symbol, limit)

    def fetch_balance(self) -> dict[str, Any]:
        return {"total": {"USD": self.cash, "USDT": self.cash}, "free": {"USD": self.cash, "USDT": self.cash}}

    def close_position(self, symbol: str, quantity: float) -> dict[str, Any]:
        return {"id": "paper-close", "symbol": symbol, "side": "sell", "amount": quantity}

    def create_market_buy_order(self, symbol: str, amount: float) -> dict[str, Any]:
        price = self.fetch_ohlcv(symbol, self.settings.timeframe, 1)[-1][4]
        cost = amount * price
        self.cash -= cost
        return {"id": "paper-buy", "symbol": symbol, "side": "buy", "amount": amount, "price": price, "cost": cost}

    def create_market_sell_order(self, symbol: str, amount: float) -> dict[str, Any]:
        price = self.fetch_ohlcv(symbol, self.settings.timeframe, 1)[-1][4]
        self.cash += amount * price
        return {"id": "paper-sell", "symbol": symbol, "side": "sell", "amount": amount, "price": price}


def _synthetic_ohlcv(symbol: str, limit: int) -> list[list[float]]:
    base_prices = {"EURUSD": 1.08, "GBPUSD": 1.27, "USDJPY": 155.0, "XAUUSD": 2350.0, "XAGUSD": 31.0, "USOIL": 78.0}
    base = base_prices.get(symbol.upper(), 100.0)
    now = int(time.time() // 60 * 60 * 1000)
    rows: list[list[float]] = []
    for index in range(limit):
        wave = math.sin(index / 7) * base * 0.002
        trend = (index - limit) * base * 0.00002
        close = base + wave + trend
        open_price = close - math.sin(index / 3) * base * 0.0005
        high = max(open_price, close) + base * 0.001
        low = min(open_price, close) - base * 0.001
        rows.append([now - (limit - index) * 60_000, open_price, high, low, close, 1000 + index])
    return rows
