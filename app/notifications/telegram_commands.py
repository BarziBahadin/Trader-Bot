from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Trade
from app.markets.sizing import calculate_position_size
from app.providers.registry import build_provider
from app.risk.risk_manager import create_stop_file, remove_stop_file
from app.services.confirmations import consume_confirmation, create_confirmation
from app.services.market_service import find_instrument, list_watchlist, require_app_state, set_active_symbol


def handle_telegram_command(text: str, db: Session, settings: Settings) -> str:
    parts = text.strip().split()
    if not parts:
        return "Send /help for commands."
    command = parts[0].lower()

    if command == "/help":
        return "\n".join(
            [
                "/status - current bot status",
                "/symbols - saved watchlist",
                "/watchlist - saved watchlist",
                "/set SYMBOL - switch active symbol",
                "/calc SYMBOL RISK% SL_DISTANCE - preview lot and margin",
                "/stop - emergency stop",
                "/resume - resume after emergency stop",
                "/sell - preview closing the open position",
                "/confirm CODE - confirm a dangerous action",
            ]
        )
    if command == "/status":
        state = require_app_state(db, settings)
        open_trade = db.query(Trade).filter(Trade.symbol == state.active_symbol, Trade.status == "open").first()
        provider_status = build_provider(state.active_provider, settings).status()
        return (
            f"Mode: {settings.bot_mode}\n"
            f"Symbol: {state.active_symbol} ({state.active_asset_class})\n"
            f"Provider: {state.active_provider} - {provider_status.message}\n"
            f"Timeframe: {state.timeframe}\n"
            f"Risk: {state.risk_percent}%\n"
            f"Lot: {state.lot_size}\n"
            f"Leverage: {state.leverage}x\n"
            f"Emergency stop: {settings.stop_file.exists()}\n"
            f"Open position: {bool(open_trade)}"
        )
    if command in {"/symbols", "/watchlist"}:
        items = list_watchlist(db)
        return "Watchlist:\n" + "\n".join(f"- {item.symbol} ({item.asset_class}, {item.provider})" for item in items)
    if command == "/set":
        if len(parts) < 2:
            return "Usage: /set XAUUSD"
        instrument = find_instrument(db, parts[1])
        if instrument is None:
            return f"Unknown symbol {parts[1]}. Use /symbols to see available markets."
        state = set_active_symbol(db, settings, instrument.symbol)
        return f"Active symbol set to {state.active_symbol} ({state.active_asset_class}, {state.active_provider})."
    if command == "/calc":
        if len(parts) < 4:
            return "Usage: /calc XAUUSD 1 50"
        instrument = find_instrument(db, parts[1])
        if instrument is None:
            return f"Unknown symbol {parts[1]}."
        risk_percent = float(parts[2])
        stop_loss_distance = float(parts[3])
        state = require_app_state(db, settings)
        provider = build_provider(instrument.provider, settings)
        try:
            candles = provider.fetch_ohlcv(instrument.symbol, state.timeframe, 1)
        except Exception:
            candles = build_provider("paper", settings).fetch_ohlcv(instrument.symbol, state.timeframe, 1)
        price = float(candles[-1][4])
        preview = calculate_position_size(
            instrument,
            settings.initial_balance,
            price,
            risk_percent,
            stop_loss_distance,
            state.take_profit_distance,
            state.leverage or instrument.default_leverage,
            settings.account_currency,
        )
        return (
            f"{instrument.symbol} size preview\n"
            f"Price: {preview.price:.5f}\n"
            f"Lot: {preview.lot_size}\n"
            f"Risk: {preview.risk_amount:.2f} {preview.account_currency}\n"
            f"Margin: {preview.margin_required:.2f} {preview.account_currency}\n"
            f"Leverage: {preview.leverage}x"
        )
    if command == "/stop":
        create_stop_file(settings.stop_file)
        return "Emergency stop enabled."
    if command == "/resume":
        remove_stop_file(settings.stop_file)
        return "Emergency stop cleared."
    if command == "/sell":
        state = require_app_state(db, settings)
        trade = db.query(Trade).filter(Trade.symbol == state.active_symbol, Trade.status == "open").first()
        if trade is None:
            return "No open position to close."
        confirmation = create_confirmation(db, "close_position", {"trade_id": trade.id, "symbol": trade.symbol, "quantity": trade.quantity})
        return f"Close {trade.symbol} position? Reply /confirm {confirmation.code} within 2 minutes."
    if command == "/confirm":
        if len(parts) < 2:
            return "Usage: /confirm CODE"
        payload = consume_confirmation(db, parts[1], "close_position")
        if payload is None:
            return "Invalid or expired confirmation code."
        trade = db.query(Trade).filter(Trade.id == payload["trade_id"], Trade.status == "open").first()
        if trade is None:
            return "Open trade not found."
        provider = build_provider(trade.provider, settings)
        provider.close_position(trade.symbol, trade.quantity)
        trade.status = "closed"
        db.commit()
        return f"Closed {trade.symbol} position."
    return "Unknown command. Send /help for commands."
