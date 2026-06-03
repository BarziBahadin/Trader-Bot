from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Signal, Trade
from app.markets.sizing import calculate_position_size
from app.providers.registry import build_provider
from app.risk.risk_manager import create_stop_file, remove_stop_file
from app.services.confirmations import consume_confirmation, create_confirmation
from app.services.execution_guard import ExecutionBlocked, assert_order_execution_allowed
from app.services.live_readiness import live_readiness
from app.services.market_service import find_instrument, list_watchlist, require_app_state, set_active_symbol


def handle_telegram_command(text: str, db: Session, settings: Settings, requester_id: str | None = None) -> str:
    parts = text.strip().split()
    if not parts:
        return "Send /help for commands."
    command = parts[0].lower()

    if command == "/help":
        return "\n".join(
            [
                "/status - current bot status",
                "/account - account equity, free balance, margin, and PnL",
                "/livecheck - show live futures readiness checks",
                "/whyhold - explain the latest hold/no-trade decision",
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
        provider = build_provider(state.active_provider, settings)
        provider_status = provider.status()
        account = _account_summary(provider)
        return (
            f"Mode: {settings.bot_mode}\n"
            f"Symbol: {state.active_symbol} ({state.active_asset_class})\n"
            f"Provider: {state.active_provider} - {provider_status.message}\n"
            f"Equity: {account.get('equity', 0):.2f} {account.get('currency', 'USDT')}\n"
            f"Free: {account.get('free', 0):.2f} {account.get('currency', 'USDT')}\n"
            f"UPnL: {account.get('unrealized_pnl', 0):.2f}\n"
            f"Timeframe: {state.timeframe}\n"
            f"Risk: {state.risk_percent}%\n"
            f"Lot: {state.lot_size}\n"
            f"Leverage: {state.leverage}x\n"
            f"Emergency stop: {settings.stop_file.exists()}\n"
            f"Open position: {bool(open_trade)}"
        )
    if command == "/account":
        state = require_app_state(db, settings)
        account = _account_summary(build_provider(state.active_provider, settings))
        currency = account.get("currency", "USDT")
        return (
            f"Account: {account.get('message', '')}\n"
            f"Equity: {account.get('equity', 0):.2f} {currency}\n"
            f"Free: {account.get('free', 0):.2f} {currency}\n"
            f"Used margin: {account.get('used', 0):.2f} {currency}\n"
            f"Unrealized PnL: {account.get('unrealized_pnl', 0):.2f} {currency}\n"
            f"Market: {account.get('market_type', '-')}\n"
            f"Margin mode: {account.get('margin_mode', '-')}"
        )
    if command == "/livecheck":
        state = require_app_state(db, settings)
        readiness = live_readiness(settings, state.active_symbol)
        lines = ["Live futures ready: " + ("YES" if readiness["ready"] else "NO")]
        for check in readiness["checks"]:
            lines.append(("OK " if check["passed"] else "NO ") + check["name"])
        lines.append(f"Max notional: {readiness['max_position_notional']}")
        lines.append(f"Max leverage: {readiness['max_leverage']}")
        return "\n".join(lines)
    if command == "/whyhold":
        state = require_app_state(db, settings)
        latest = db.query(Signal).filter(Signal.symbol == state.active_symbol).order_by(Signal.id.desc()).first()
        if latest:
            return (
                f"Latest {state.active_symbol} signal: {latest.signal}\n"
                f"Reason: {latest.reason or 'no reason recorded yet'}\n"
                f"Price: {latest.price}\n"
                f"RSI: {latest.rsi}\n"
                f"Fast MA: {latest.fast_ma}\n"
                f"Slow MA: {latest.slow_ma}"
            )
        return f"No signal recorded yet for {state.active_symbol}."
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
        try:
            risk_percent = float(parts[2])
            stop_loss_distance = float(parts[3])
        except ValueError:
            return "Usage: /calc SYMBOL RISK% SL_DISTANCE. Example: /calc BTC/USDT:USDT 1 50"
        if risk_percent <= 0 or risk_percent > 5 or stop_loss_distance <= 0:
            return "Risk must be 0-5% and stop-loss distance must be positive."
        state = require_app_state(db, settings)
        provider = build_provider(instrument.provider, settings)
        try:
            candles = provider.fetch_ohlcv(instrument.symbol, state.timeframe, 1)
        except Exception:
            if settings.bot_mode == "live":
                return f"{instrument.provider} market data unavailable for {instrument.symbol}."
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
        confirmation = create_confirmation(
            db,
            "close_position",
            {"trade_id": trade.id, "symbol": trade.symbol, "quantity": trade.quantity},
            requester_id=requester_id,
        )
        return f"Close {trade.symbol} position? Reply /confirm {confirmation.code} within 2 minutes."
    if command == "/confirm":
        if len(parts) < 2:
            return "Usage: /confirm CODE"
        payload = consume_confirmation(db, parts[1], "close_position", requester_id=requester_id)
        if payload is None:
            return "Invalid or expired confirmation code."
        trade = db.query(Trade).filter(Trade.id == payload["trade_id"], Trade.status == "open").first()
        if trade is None:
            return "Open trade not found."
        try:
            assert_order_execution_allowed(settings, trade.provider, trade.symbol)
            provider = build_provider(trade.provider, settings)
            provider.close_position(trade.symbol, trade.quantity)
        except ExecutionBlocked as exc:
            return f"Close blocked: {exc}"
        trade.status = "closed"
        db.commit()
        return f"Closed {trade.symbol} position."
    return "Unknown command. Send /help for commands."


def _account_summary(provider) -> dict:
    if hasattr(provider, "account_summary"):
        try:
            return provider.account_summary()
        except Exception as exc:
            return {"equity": 0.0, "free": 0.0, "used": 0.0, "unrealized_pnl": 0.0, "message": exc.__class__.__name__}
    try:
        balance = provider.fetch_balance()
    except Exception as exc:
        return {"equity": 0.0, "free": 0.0, "used": 0.0, "unrealized_pnl": 0.0, "message": exc.__class__.__name__}
    return {
        "currency": "USDT",
        "equity": float((balance.get("total") or {}).get("USDT") or 0.0),
        "free": float((balance.get("free") or {}).get("USDT") or 0.0),
        "used": float((balance.get("used") or {}).get("USDT") or 0.0),
        "unrealized_pnl": 0.0,
        "message": "balance loaded",
    }
