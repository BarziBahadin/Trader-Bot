from __future__ import annotations

from app.config import Settings
from app.services.live_readiness import live_readiness


class ExecutionBlocked(RuntimeError):
    pass


def assert_order_execution_allowed(settings: Settings, provider_name: str, symbol: str) -> None:
    provider = provider_name.lower()
    if settings.bot_mode == "live":
        readiness = live_readiness(settings, symbol)
        if not readiness["ready"]:
            failed = ", ".join(check["name"] for check in readiness["checks"] if not check["passed"])
            raise ExecutionBlocked(f"live trading blocked: {failed}")
        return
    if provider == "paper":
        if settings.bot_mode == "backtest":
            raise ExecutionBlocked("backtest mode cannot execute orders")
        return
    if settings.bot_mode == "testnet":
        if not settings.okx_demo:
            raise ExecutionBlocked("testnet mode requires OKX_DEMO=true before non-paper orders are allowed")
        return
    raise ExecutionBlocked(f"{settings.bot_mode} mode cannot execute non-paper orders")
