from typing import Any

import ccxt

from app.exchange.base import ExchangeClient


class PaperBroker(ExchangeClient):
    def __init__(self, initial_balance: float):
        self.cash = initial_balance
        self.positions: dict[str, float] = {}
        self.last_prices: dict[str, float] = {}
        self.market_data = ccxt.binance({"enableRateLimit": True})

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 200) -> list[list[float]]:
        return self.market_data.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    def fetch_balance(self) -> dict[str, Any]:
        return {"total": {"USDT": self.cash}, "free": {"USDT": self.cash}, "positions": self.positions.copy()}

    def set_last_price(self, symbol: str, price: float) -> None:
        self.last_prices[symbol] = price

    def create_market_buy_order(self, symbol: str, amount: float) -> dict[str, Any]:
        price = self._price(symbol)
        cost = amount * price
        if cost > self.cash:
            raise ValueError("insufficient paper balance")
        self.cash -= cost
        self.positions[symbol] = self.positions.get(symbol, 0.0) + amount
        return {"id": "paper-buy", "symbol": symbol, "side": "buy", "amount": amount, "price": price, "cost": cost}

    def create_market_sell_order(self, symbol: str, amount: float) -> dict[str, Any]:
        price = self._price(symbol)
        held = self.positions.get(symbol, 0.0)
        if amount > held:
            raise ValueError("insufficient paper position")
        self.positions[symbol] = held - amount
        self.cash += amount * price
        return {"id": "paper-sell", "symbol": symbol, "side": "sell", "amount": amount, "price": price}

    def _price(self, symbol: str) -> float:
        price = self.last_prices.get(symbol)
        if not price:
            raise ValueError(f"no last price set for {symbol}")
        return price
