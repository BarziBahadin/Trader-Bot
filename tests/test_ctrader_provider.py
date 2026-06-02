from app.config import Settings
from app.providers.ctrader_provider import CTraderProvider


def test_ctrader_provider_reports_missing_credentials():
    status = CTraderProvider(Settings()).status()

    assert status.connected is False
    assert "CTRADER_CLIENT_ID" in status.message


def test_ctrader_provider_lists_default_forex_metals_symbols():
    symbols = {instrument.symbol for instrument in CTraderProvider(Settings()).instruments()}

    assert "EURUSD" in symbols
    assert "XAUUSD" in symbols
