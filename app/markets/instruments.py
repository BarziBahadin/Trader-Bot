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
    Instrument("BTC/USDT:USDT", "Bitcoin USDT perpetual", "crypto", "okx", "BTC", "USDT", 2, 0.01, 1, 0.01, 0.01, 10),
    Instrument("ETH/USDT:USDT", "Ethereum USDT perpetual", "crypto", "okx", "ETH", "USDT", 2, 0.01, 1, 0.01, 0.01, 10),
    Instrument("SOL/USDT:USDT", "Solana USDT perpetual", "crypto", "okx", "SOL", "USDT", 3, 0.001, 1, 0.01, 0.01, 10),
    Instrument("BTC/USDT", "Bitcoin / Tether", "crypto", "okx", "BTC", "USDT", 2, 0.01, 1, 0.00001, 0.00001, 1),
    Instrument("ETH/USDT", "Ethereum / Tether", "crypto", "okx", "ETH", "USDT", 2, 0.01, 1, 0.0001, 0.0001, 1),
    Instrument("SOL/USDT", "Solana / Tether", "crypto", "okx", "SOL", "USDT", 3, 0.001, 1, 0.001, 0.001, 1),
    Instrument("PAXG/USDT", "PAX Gold / Tether", "metals", "okx", "PAXG", "USDT", 2, 0.01, 1, 0.0001, 0.0001, 1),
    Instrument("XAUT/USDT", "Tether Gold / Tether", "metals", "okx", "XAUT", "USDT", 2, 0.01, 1, 0.0001, 0.0001, 1),
    Instrument("EUR/USDT", "Euro / Tether", "forex", "okx", "EUR", "USDT", 5, 0.00001, 1, 0.01, 0.01, 1),
    Instrument("EURC/USDT", "Euro Coin / Tether", "forex", "okx", "EURC", "USDT", 5, 0.00001, 1, 0.01, 0.01, 1),
    Instrument("XAUUSD", "Gold / US Dollar preview", "metals", "okx", "XAU", "USD", 2, 0.01, 100, 0.01, 0.01, 20, trade_enabled=False),
    Instrument("USOIL", "US Oil preview", "commodities", "okx", "OIL", "USD", 2, 0.01, 1_000, 0.01, 0.01, 10, trade_enabled=False),
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
