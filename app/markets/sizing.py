from __future__ import annotations

from dataclasses import asdict, dataclass
from math import floor

from app.markets.instruments import Instrument


@dataclass(frozen=True)
class PositionSizePreview:
    symbol: str
    asset_class: str
    price: float
    risk_percent: float
    risk_amount: float
    stop_loss_distance: float
    take_profit_distance: float
    stop_loss_price: float
    take_profit_price: float
    leverage: float
    lot_size: float
    quantity: float
    contract_size: float
    notional: float
    margin_required: float
    pip_or_tick_value: float
    account_currency: str

    def to_dict(self) -> dict:
        return asdict(self)


def round_volume(volume: float, instrument: Instrument) -> float:
    if volume <= instrument.volume_min:
        return instrument.volume_min
    steps = floor((volume - instrument.volume_min) / instrument.volume_step)
    return round(instrument.volume_min + steps * instrument.volume_step, 8)


def calculate_position_size(
    instrument: Instrument,
    account_balance: float,
    price: float,
    risk_percent: float,
    stop_loss_distance: float,
    take_profit_distance: float | None = None,
    leverage: float | None = None,
    account_currency: str = "USD",
) -> PositionSizePreview:
    if account_balance <= 0:
        raise ValueError("account balance must be positive")
    if price <= 0:
        raise ValueError("price must be positive")
    if risk_percent <= 0:
        raise ValueError("risk percent must be positive")
    if stop_loss_distance <= 0:
        raise ValueError("stop loss distance must be positive")

    leverage_value = leverage or instrument.default_leverage
    take_profit = take_profit_distance if take_profit_distance and take_profit_distance > 0 else stop_loss_distance * 2
    risk_amount = account_balance * (risk_percent / 100)
    contract_size = instrument.contract_size
    value_per_price_unit = contract_size
    raw_lots = risk_amount / (stop_loss_distance * value_per_price_unit)
    lot_size = round_volume(raw_lots, instrument)
    quantity = lot_size * contract_size
    notional = quantity * price
    margin_required = notional / leverage_value
    pip_or_tick_value = instrument.tick_value or (instrument.point * contract_size * lot_size)

    return PositionSizePreview(
        symbol=instrument.symbol,
        asset_class=instrument.asset_class,
        price=price,
        risk_percent=risk_percent,
        risk_amount=risk_amount,
        stop_loss_distance=stop_loss_distance,
        take_profit_distance=take_profit,
        stop_loss_price=price - stop_loss_distance,
        take_profit_price=price + take_profit,
        leverage=leverage_value,
        lot_size=lot_size,
        quantity=quantity,
        contract_size=contract_size,
        notional=notional,
        margin_required=margin_required,
        pip_or_tick_value=pip_or_tick_value,
        account_currency=account_currency,
    )
