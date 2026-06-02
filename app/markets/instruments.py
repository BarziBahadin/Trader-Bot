from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Instrument:
    symbol: str
    display_name: str
    asset_class: str
    provider: str
    base_currency: str
    quote_currency: str
    digits: int
    point: float
    contract_size: float
    volume_min: float
    volume_step: float
    default_leverage: float
    tick_value: float | None = None
    spread: float | None = None
    trade_enabled: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_INSTRUMENTS: list[Instrument] = [
    Instrument("BTC/USDT", "Bitcoin / Tether", "crypto", "binance", "BTC", "USDT", 2, 0.01, 1, 0.00001, 0.00001, 1),
    Instrument("ETH/USDT", "Ethereum / Tether", "crypto", "binance", "ETH", "USDT", 2, 0.01, 1, 0.0001, 0.0001, 1),
    Instrument("EURUSD", "Euro / US Dollar", "forex", "ctrader", "EUR", "USD", 5, 0.00001, 100_000, 0.01, 0.01, 30),
    Instrument("GBPUSD", "British Pound / US Dollar", "forex", "ctrader", "GBP", "USD", 5, 0.00001, 100_000, 0.01, 0.01, 30),
    Instrument("USDJPY", "US Dollar / Yen", "forex", "ctrader", "USD", "JPY", 3, 0.001, 100_000, 0.01, 0.01, 30),
    Instrument("XAUUSD", "Gold / US Dollar", "metals", "ctrader", "XAU", "USD", 2, 0.01, 100, 0.01, 0.01, 20),
    Instrument("XAGUSD", "Silver / US Dollar", "metals", "ctrader", "XAG", "USD", 3, 0.001, 5_000, 0.01, 0.01, 20),
    Instrument("USOIL", "US Oil", "commodities", "ctrader", "OIL", "USD", 2, 0.01, 1_000, 0.01, 0.01, 10),
]


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def infer_asset_class(symbol: str) -> str:
    normalized = normalize_symbol(symbol).replace("/", "")
    if normalized in {"XAUUSD", "XAGUSD"}:
        return "metals"
    if normalized in {"USOIL", "UKOIL", "WTI", "BRENT"}:
        return "commodities"
    if "/" in symbol or normalized.endswith(("USDT", "BTC", "ETH")):
        return "crypto"
    if len(normalized) == 6:
        return "forex"
    return "commodities"


def default_instrument(symbol: str, provider: str = "paper") -> Instrument:
    normalized = normalize_symbol(symbol)
    for instrument in DEFAULT_INSTRUMENTS:
        if normalize_symbol(instrument.symbol) == normalized:
            return Instrument(**{**instrument.to_dict(), "provider": provider if provider == "paper" else instrument.provider})
    asset_class = infer_asset_class(normalized)
    return Instrument(
        symbol=normalized,
        display_name=normalized,
        asset_class=asset_class,
        provider=provider,
        base_currency=normalized[:3],
        quote_currency=normalized[3:6] if len(normalized) >= 6 else "USD",
        digits=5 if asset_class == "forex" else 2,
        point=0.00001 if asset_class == "forex" else 0.01,
        contract_size=100_000 if asset_class == "forex" else 100,
        volume_min=0.01,
        volume_step=0.01,
        default_leverage=30 if asset_class == "forex" else 20,
    )


def default_watchlist() -> list[str]:
    return [instrument.symbol for instrument in DEFAULT_INSTRUMENTS]
