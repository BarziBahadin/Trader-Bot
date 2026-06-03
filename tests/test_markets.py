from app.markets.instruments import default_instrument, infer_asset_class
from app.markets.sizing import calculate_position_size


def test_infers_asset_classes():
    assert infer_asset_class("BTC/USDT") == "crypto"
    assert infer_asset_class("EURUSD") == "forex"
    assert infer_asset_class("XAUUSD") == "metals"
    assert infer_asset_class("USOIL") == "commodities"


def test_calculates_lot_margin_and_risk():
    instrument = default_instrument("XAUUSD", "okx")

    preview = calculate_position_size(
        instrument,
        account_balance=10_000,
        price=2350,
        risk_percent=1,
        stop_loss_distance=50,
        take_profit_distance=100,
        leverage=20,
    )

    assert preview.lot_size > 0
    assert preview.risk_amount == 100
    assert preview.margin_required > 0
    assert preview.stop_loss_price == 2300
