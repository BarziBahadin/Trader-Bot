from __future__ import annotations

from app.config import Settings


def live_readiness(settings: Settings, symbol: str) -> dict:
    checks = [
        ("BOT_MODE=live", settings.bot_mode == "live"),
        ("ENABLE_REAL_TRADING=true", settings.enable_real_trading),
        ("PROVIDER=okx", settings.provider == "okx"),
        ("OKX_DEMO=false", not settings.okx_demo),
        ("OKX_MARKET_TYPE=swap", settings.okx_market_type in {"swap", "future", "futures"}),
        ("OKX_API_KEY set", bool(settings.okx_api_key)),
        ("OKX_API_SECRET set", bool(settings.okx_api_secret)),
        ("OKX_PASSPHRASE set", bool(settings.okx_passphrase)),
        ("LIVE_TRADING_ACK set", settings.live_trading_ack == "I_UNDERSTAND_LIVE_FUTURES_RISK"),
        ("API_AUTH_TOKEN set", bool(settings.api_auth_token)),
        ("swap symbol selected", ":USDT" in symbol),
        ("leverage within cap", settings.default_leverage <= settings.max_leverage),
    ]
    return {
        "ready": all(passed for _, passed in checks),
        "symbol": symbol,
        "checks": [{"name": name, "passed": passed} for name, passed in checks],
        "max_position_notional": settings.max_position_notional,
        "max_leverage": settings.max_leverage,
    }
