from app.config import Settings
from app.providers.okx_provider import OkxProvider


def test_okx_provider_allows_public_market_data_without_keys():
    status = OkxProvider(Settings(OKX_API_KEY="", OKX_API_SECRET="", OKX_PASSPHRASE="")).status()

    assert status.connected is True
    assert "public market data" in status.message


def test_okx_account_summary_reports_missing_keys():
    summary = OkxProvider(Settings(OKX_API_KEY="", OKX_API_SECRET="", OKX_PASSPHRASE="")).account_summary()

    assert summary["connected"] is False
    assert summary["equity"] == 0.0


def test_okx_provider_lists_default_symbols_without_network():
    provider = OkxProvider(Settings(OKX_API_KEY="", OKX_API_SECRET="", OKX_PASSPHRASE=""))
    provider.exchange.load_markets = lambda: {}
    symbols = {instrument.symbol for instrument in provider.instruments()}

    assert "BTC/USDT" in symbols
    assert "BTC/USDT:USDT" in symbols
    assert "PAXG/USDT" in symbols
