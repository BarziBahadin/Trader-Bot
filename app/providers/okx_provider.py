from __future__ import annotations

from typing import Any

import ccxt

from app.config import Settings
from app.markets.instruments import DEFAULT_INSTRUMENTS, Instrument, infer_asset_class
from app.providers.base import MarketProvider, ProviderStatus


class OkxProvider(MarketProvider):
    name = "okx"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.exchange = ccxt.okx(
            {
                "apiKey": settings.okx_api_key,
                "secret": settings.okx_api_secret,
                "password": settings.okx_passphrase,
                "enableRateLimit": True,
                "options": {"defaultType": settings.okx_market_type},
            }
        )
        if settings.okx_demo:
            self.exchange.headers = {**getattr(self.exchange, "headers", {}), "x-simulated-trading": "1"}
            try:
                self.exchange.set_sandbox_mode(True)
            except Exception:
                pass

    @property
    def has_private_credentials(self) -> bool:
        return bool(self.settings.okx_api_key and self.settings.okx_api_secret and self.settings.okx_passphrase)

    def status(self) -> ProviderStatus:
        if self.has_private_credentials:
            mode = "demo" if self.settings.okx_demo else "live"
            return ProviderStatus(self.name, True, f"OKX {mode} {self.settings.okx_market_type} API configured")
        return ProviderStatus(self.name, True, "OKX public market data active; trading keys missing")

    def instruments(self) -> list[Instrument]:
        instruments = [instrument for instrument in DEFAULT_INSTRUMENTS if instrument.provider == "okx"]
        try:
            markets = self.exchange.load_markets()
        except Exception:
            return instruments

        existing = {instrument.symbol for instrument in instruments}
        for symbol, market in markets.items():
            if symbol in existing or not market.get("active", True):
                continue
            if market.get("spot") or market.get("swap") or market.get("future"):
                instruments.append(_instrument_from_market(symbol, market))
        return instruments

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 200) -> list[list[float]]:
        return self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    def fetch_balance(self) -> dict[str, Any]:
        if not self.has_private_credentials:
            return {"total": {"USDT": 0.0}, "free": {"USDT": 0.0}}
        return self.exchange.fetch_balance()

    def account_summary(self) -> dict[str, Any]:
        if not self.has_private_credentials:
            return {
                "connected": False,
                "currency": "USDT",
                "equity": 0.0,
                "free": 0.0,
                "used": 0.0,
                "total": 0.0,
                "unrealized_pnl": 0.0,
                "message": "OKX trading keys are missing",
            }
        try:
            balance = self.fetch_balance()
        except Exception as exc:
            return {
                "connected": False,
                "currency": "USDT",
                "equity": 0.0,
                "free": 0.0,
                "used": 0.0,
                "total": 0.0,
                "unrealized_pnl": 0.0,
                "market_type": self.settings.okx_market_type,
                "margin_mode": self.settings.okx_margin_mode,
                "demo": self.settings.okx_demo,
                "message": f"OKX account error: {exc.__class__.__name__}",
            }
        currency = "USDT" if "USDT" in (balance.get("total") or {}) else self.settings.account_currency
        total = _balance_value(balance, "total", currency)
        free = _balance_value(balance, "free", currency)
        used = _balance_value(balance, "used", currency)
        equity = total
        unrealized_pnl = 0.0
        info = balance.get("info") or {}
        data = info.get("data") or []
        if data:
            details = data[0].get("details") or []
            for detail in details:
                if detail.get("ccy") == currency:
                    equity = _float(detail.get("eq"), total)
                    free = _float(detail.get("availBal"), free)
                    used = _float(detail.get("frozenBal"), used)
                    unrealized_pnl = _float(detail.get("upl"), 0.0)
                    break
        return {
            "connected": True,
            "currency": currency,
            "equity": equity,
            "free": free,
            "used": used,
            "total": total,
            "unrealized_pnl": unrealized_pnl,
            "market_type": self.settings.okx_market_type,
            "margin_mode": self.settings.okx_margin_mode,
            "demo": self.settings.okx_demo,
            "message": "OKX demo account connected" if self.settings.okx_demo else "OKX live account connected",
        }

    def close_position(self, symbol: str, quantity: float) -> dict[str, Any]:
        if not self.has_private_credentials:
            raise RuntimeError("OKX trading keys are missing")
        amount = self._order_amount(symbol, quantity)
        return self.exchange.create_market_sell_order(symbol, amount, params={**self._order_params(), "reduceOnly": True})

    def create_market_buy_order(self, symbol: str, amount: float) -> dict[str, Any]:
        if not self.has_private_credentials:
            raise RuntimeError("OKX trading keys are missing")
        self._set_leverage(symbol)
        return self.exchange.create_market_buy_order(symbol, self._order_amount(symbol, amount), params=self._order_params())

    def create_market_sell_order(self, symbol: str, amount: float) -> dict[str, Any]:
        return self.close_position(symbol, amount)

    def _order_params(self) -> dict[str, Any]:
        if self.settings.okx_market_type in {"swap", "future", "futures"}:
            return {"tdMode": self.settings.okx_margin_mode}
        return {}

    def _set_leverage(self, symbol: str) -> None:
        if self.settings.okx_market_type not in {"swap", "future", "futures"}:
            return
        try:
            self.exchange.set_leverage(
                int(self.settings.default_leverage),
                symbol,
                params={"mgnMode": self.settings.okx_margin_mode},
            )
        except Exception:
            # Some accounts require leverage to be set in the OKX UI first.
            pass

    def _order_amount(self, symbol: str, base_quantity: float) -> float:
        markets = self.exchange.load_markets()
        market = markets.get(symbol) or self.exchange.market(symbol)
        amount = float(base_quantity)
        if market.get("swap") or market.get("future"):
            contract_size = float(market.get("contractSize") or 1.0)
            amount = amount / contract_size
        limits = market.get("limits") or {}
        amount_limits = limits.get("amount") or {}
        minimum = amount_limits.get("min")
        if minimum is not None and amount < float(minimum):
            amount = float(minimum)
        return float(self.exchange.amount_to_precision(symbol, amount))


def _instrument_from_market(symbol: str, market: dict) -> Instrument:
    asset_class = infer_asset_class(symbol)
    base = str(market.get("base") or symbol.split("/")[0])
    quote = str(market.get("quote") or (symbol.split("/")[1] if "/" in symbol else "USDT"))
    precision = market.get("precision") or {}
    limits = market.get("limits") or {}
    amount_limits = limits.get("amount") or {}
    price_precision = precision.get("price")
    amount_precision = precision.get("amount")
    point = 10 ** -int(price_precision) if isinstance(price_precision, int) and price_precision >= 0 else 0.01
    volume_step = 10 ** -int(amount_precision) if isinstance(amount_precision, int) and amount_precision >= 0 else 0.0001
    volume_min = float(amount_limits.get("min") or volume_step)
    contract_size = float(market.get("contractSize") or 1)
    return Instrument(
        symbol=symbol,
        display_name=market.get("id") or symbol,
        asset_class=asset_class,
        provider="okx",
        base_currency=base,
        quote_currency=quote,
        digits=int(price_precision) if isinstance(price_precision, int) else 2,
        point=point,
        contract_size=contract_size,
        volume_min=volume_min,
        volume_step=volume_step,
        default_leverage=1,
        trade_enabled=bool(market.get("active", True)),
    )


def _balance_value(balance: dict, bucket: str, currency: str) -> float:
    return _float((balance.get(bucket) or {}).get(currency), 0.0)


def _float(value: Any, default: float) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
