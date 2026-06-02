from __future__ import annotations

import time

from app.config import Settings
from app.data.market_data import MarketData
from app.db.database import SessionLocal, init_db
from app.db.models import Trade
from app.execution.order_manager import OrderManager
from app.notifications.telegram import TelegramNotifier
from app.providers.registry import build_provider
from app.services.market_service import require_app_state, seed_market_defaults
from app.strategy.rsi_ma_strategy import RsiMaStrategy
from app.utils.logger import logger


def run_trading_worker(settings: Settings, interval_seconds: int = 60) -> None:
    init_db()
    if settings.bot_mode == "live" and not settings.enable_real_trading:
        logger.warning("Live mode blocked unless ENABLE_REAL_TRADING=true")
        return

    notifier = TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)
    notifier.send(f"Bot started in {settings.bot_mode} mode")
    logger.info("Trading worker started in {} mode", settings.bot_mode)

    while True:
        try:
            if settings.stop_file.exists():
                logger.warning("Emergency stop file exists; trading paused")
                time.sleep(30)
                continue
            _run_once(settings, notifier)
        except Exception as exc:
            logger.warning("Trading worker iteration failed: {}", exc)
        time.sleep(interval_seconds)


def _run_once(settings: Settings, notifier: TelegramNotifier) -> None:
    with SessionLocal() as db:
        seed_market_defaults(db, settings)
        state = require_app_state(db, settings)
        settings.symbol = state.active_symbol
        settings.provider = state.active_provider
        settings.asset_class = state.active_asset_class
        settings.timeframe = state.timeframe

        provider = build_provider(state.active_provider, settings)
        candles = MarketData(provider).candles(state.active_symbol, state.timeframe)
        open_position = db.query(Trade).filter(Trade.symbol == state.active_symbol, Trade.status == "open").first()
        entry_price = open_position.entry_price if open_position else None
        decision = RsiMaStrategy(settings).evaluate(candles, open_position is not None, entry_price)
        if decision.signal != "hold":
            notifier.send(f"{state.active_symbol} {decision.signal.upper()} signal: {decision.reason}")
        OrderManager(settings, provider, notifier).handle_decision(db, decision)
