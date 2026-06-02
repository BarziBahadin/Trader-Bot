from __future__ import annotations

from typing import Any

from app.config import Settings
from app.markets.instruments import DEFAULT_INSTRUMENTS, Instrument
from app.providers.base import MarketProvider, ProviderStatus


class CTraderProvider(MarketProvider):
    name = "ctrader"

    def __init__(self, settings: Settings):
        self.settings = settings

    def status(self) -> ProviderStatus:
        missing = []
        if not self.settings.ctrader_client_id:
            missing.append("CTRADER_CLIENT_ID")
        if not self.settings.ctrader_client_secret:
            missing.append("CTRADER_CLIENT_SECRET")
        if not self.settings.ctrader_access_token:
            missing.append("CTRADER_ACCESS_TOKEN")
        if not self.settings.ctrader_account_id:
            missing.append("CTRADER_ACCOUNT_ID")
        if missing:
            return ProviderStatus(self.name, False, f"cTrader credentials missing: {', '.join(missing)}")
        return ProviderStatus(self.name, False, "cTrader adapter configured; API session implementation pending")

    def instruments(self) -> list[Instrument]:
        return [instrument for instrument in DEFAULT_INSTRUMENTS if instrument.provider == "ctrader"]

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 200) -> list[list[float]]:
        raise RuntimeError(self.status().message)

    def fetch_balance(self) -> dict[str, Any]:
        return {"total": {self.settings.account_currency: 0.0}, "free": {self.settings.account_currency: 0.0}}

    def close_position(self, symbol: str, quantity: float) -> dict[str, Any]:
        raise RuntimeError(self.status().message)
