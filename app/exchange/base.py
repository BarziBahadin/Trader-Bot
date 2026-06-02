from abc import ABC, abstractmethod
from typing import Any


class ExchangeClient(ABC):
    @abstractmethod
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 200) -> list[list[float]]:
        raise NotImplementedError

    @abstractmethod
    def fetch_balance(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def create_market_buy_order(self, symbol: str, amount: float) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def create_market_sell_order(self, symbol: str, amount: float) -> dict[str, Any]:
        raise NotImplementedError

