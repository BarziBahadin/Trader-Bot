from app.config import Settings
from app.services.live_readiness import live_readiness


def test_live_readiness_blocks_half_configured_live_mode():
    settings = Settings(
        BOT_MODE="live",
        ENABLE_REAL_TRADING=True,
        PROVIDER="okx",
        OKX_DEMO=False,
        OKX_API_KEY="",
        OKX_API_SECRET="",
        OKX_PASSPHRASE="",
    )

    result = live_readiness(settings, "BTC/USDT:USDT")

    assert result["ready"] is False
    failed = {check["name"] for check in result["checks"] if not check["passed"]}
    assert "OKX_API_KEY set" in failed
    assert "LIVE_TRADING_ACK set" in failed


def test_live_readiness_passes_with_live_futures_inputs():
    settings = Settings(
        BOT_MODE="live",
        ENABLE_REAL_TRADING=True,
        PROVIDER="okx",
        OKX_DEMO=False,
        OKX_API_KEY="key",
        OKX_API_SECRET="secret",
        OKX_PASSPHRASE="pass",
        LIVE_TRADING_ACK="I_UNDERSTAND_LIVE_FUTURES_RISK",
        API_AUTH_TOKEN="token",
        DEFAULT_LEVERAGE=2,
        MAX_LEVERAGE=3,
    )

    result = live_readiness(settings, "BTC/USDT:USDT")

    assert result["ready"] is True


def test_paper_mode_is_not_live_ready_even_with_okx_keys():
    settings = Settings(
        BOT_MODE="paper",
        PROVIDER="okx",
        OKX_DEMO=False,
        OKX_API_KEY="key",
        OKX_API_SECRET="secret",
        OKX_PASSPHRASE="pass",
        LIVE_TRADING_ACK="I_UNDERSTAND_LIVE_FUTURES_RISK",
    )

    result = live_readiness(settings, "BTC/USDT:USDT")

    assert result["ready"] is False


def test_live_readiness_requires_api_auth_token_for_live_futures():
    settings = Settings(
        BOT_MODE="live",
        ENABLE_REAL_TRADING=True,
        PROVIDER="okx",
        OKX_DEMO=False,
        OKX_API_KEY="key",
        OKX_API_SECRET="secret",
        OKX_PASSPHRASE="pass",
        LIVE_TRADING_ACK="I_UNDERSTAND_LIVE_FUTURES_RISK",
        API_AUTH_TOKEN="",
    )

    result = live_readiness(settings, "BTC/USDT:USDT")

    assert result["ready"] is False
    failed = {check["name"] for check in result["checks"] if not check["passed"]}
    assert "API_AUTH_TOKEN set" in failed
