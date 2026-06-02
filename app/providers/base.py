from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.markets.instruments import Instrument


@dataclass(frozen=True)
class ProviderStatus:
    name: str
    connected: bool
    message: str


class MarketProvider(ABC):
    name: str

    @abstractmethod
    def status(self) -> ProviderStatus:
        raise NotImplementedError

    @abstractmethod
    def instruments(self) -> list[Instrument]:
        raise NotImplementedError

    @abstractmethod
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 200) -> list[list[float]]:
        raise NotImplementedError

    @abstractmethod
    def fetch_balance(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def close_position(self, symbol: str, quantity: float) -> dict[str, Any]:
        raise NotImplementedError
