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
from app.services.market_service import find_instrument, list_watchlist, require_app_state, set_active_symbol, update_state


TIMEFRAMES = {"1m", "5m", "15m", "30m", "1h", "4h", "1d"}


def handle_telegram_command(text: str, db: Session, settings: Settings, requester_id: str | None = None) -> str:
    parts = text.strip().split()
    if not parts:
        return _welcome_message()
    command = _normalize_command(parts[0])

    if command in {"/start", "/menu", "/help"}:
        return _welcome_message()
    if command == "/status":
        state = require_app_state(db, settings)
        open_trade = db.query(Trade).filter(Trade.symbol == state.active_symbol, Trade.status == "open").first()
        provider = build_provider(state.active_provider, settings)
        provider_status = provider.status()
        account = _account_summary(provider)
        return (
            "Bot status\n"
            f"Mode: {settings.bot_mode.upper()}\n"
            f"Market: {state.active_symbol} ({state.active_asset_class})\n"
            f"Provider: {state.active_provider} - {provider_status.message}\n"
            f"Timeframe: {state.timeframe}\n"
            f"Equity: {_money(account.get('equity', 0))} {account.get('currency', 'USDT')}\n"
            f"Free: {_money(account.get('free', 0))} {account.get('currency', 'USDT')}\n"
            f"Unrealized PnL: {_money(account.get('unrealized_pnl', 0))}\n"
            f"Risk per trade: {state.risk_percent}%\n"
            f"Stop distance: {state.stop_loss_distance}\n"
            f"Take profit distance: {state.take_profit_distance}\n"
            f"Leverage: {state.leverage}x\n"
            f"Emergency stop: {'ON' if settings.stop_file.exists() else 'OFF'}\n"
            f"Open position: {'YES' if open_trade else 'NO'}\n\n"
            "Useful next commands:\n"
            "/whyhold - why it did not trade\n"
            "/calc - preview size\n"
            "/sell - close current position"
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
    if command in {"/whyhold", "/why"}:
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
    if command in {"/symbols", "/watchlist", "/markets"}:
        items = list_watchlist(db)
        state = require_app_state(db, settings)
        return _watchlist_message(items, state.active_symbol)
    if command == "/set":
        if len(parts) < 2:
            return "Tell me the market to use.\nExample: /set BTC/USDT:USDT\nUse /symbols to see your list."
        instrument = find_instrument(db, parts[1])
        if instrument is None:
            return f"I do not know {parts[1]} yet.\nUse /symbols to see available markets."
        state = set_active_symbol(db, settings, instrument.symbol)
        return (
            f"Active market changed to {state.active_symbol}\n"
            f"Type: {state.active_asset_class}\n"
            f"Provider: {state.active_provider}\n\n"
            "Next: /status or /calc"
        )
    if command == "/timeframe":
        if len(parts) < 2 or parts[1] not in TIMEFRAMES:
            return "Choose a timeframe: /timeframe 15m\nAllowed: 1m, 5m, 15m, 30m, 1h, 4h, 1d"
        state = update_state(db, settings, {"timeframe": parts[1]})
        return f"Timeframe changed to {state.timeframe}."
    if command == "/risk":
        state = require_app_state(db, settings)
        return (
            "Risk settings\n"
            f"Risk per trade: {state.risk_percent}%\n"
            f"Stop distance: {state.stop_loss_distance}\n"
            f"Take profit distance: {state.take_profit_distance}\n"
            f"Leverage: {state.leverage}x\n\n"
            "Change it like this:\n"
            "/setrisk 1 50 100 2\n"
            "That means: 1% risk, 50 stop distance, 100 take profit distance, 2x leverage."
        )
    if command == "/setrisk":
        if len(parts) < 5:
            return "Usage: /setrisk RISK% STOP_DISTANCE TAKE_PROFIT_DISTANCE LEVERAGE\nExample: /setrisk 1 50 100 2"
        try:
            risk_percent = float(parts[1])
            stop_loss_distance = float(parts[2])
            take_profit_distance = float(parts[3])
            leverage = float(parts[4])
        except ValueError:
            return "Those numbers did not look right.\nExample: /setrisk 1 50 100 2"
        if risk_percent <= 0 or risk_percent > 5:
            return "Risk must be more than 0 and no more than 5%."
        if stop_loss_distance <= 0 or take_profit_distance <= 0 or leverage <= 0:
            return "Stop distance, take profit distance, and leverage must be positive numbers."
        if leverage > settings.max_leverage:
            return f"Leverage is capped at {settings.max_leverage}x."
        state = update_state(
            db,
            settings,
            {
                "risk_percent": risk_percent,
                "stop_loss_distance": stop_loss_distance,
                "take_profit_distance": take_profit_distance,
                "leverage": leverage,
            },
        )
        return (
            "Risk updated\n"
            f"Risk: {state.risk_percent}%\n"
            f"Stop distance: {state.stop_loss_distance}\n"
            f"Take profit distance: {state.take_profit_distance}\n"
            f"Leverage: {state.leverage}x"
        )
    if command in {"/calc", "/size"}:
        if len(parts) < 4:
            state = require_app_state(db, settings)
            return (
                "Preview position size before the bot trades.\n"
                f"Example for current market: /calc {state.active_symbol} {state.risk_percent} {state.stop_loss_distance}\n"
                "Format: /calc SYMBOL RISK% STOP_DISTANCE"
            )
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
            f"Size preview for {instrument.symbol}\n"
            f"Price: {preview.price:.5f}\n"
            f"Lot: {preview.lot_size}\n"
            f"Risk amount: {_money(preview.risk_amount)} {preview.account_currency}\n"
            f"Margin needed: {_money(preview.margin_required)} {preview.account_currency}\n"
            f"Leverage: {preview.leverage}x\n\n"
            "This is only a preview. It does not open a trade."
        )
    if command == "/stop":
        create_stop_file(settings.stop_file)
        return "Emergency stop is ON.\nThe bot will not open new trades until you send /resume."
    if command == "/resume":
        remove_stop_file(settings.stop_file)
        return "Emergency stop is OFF.\nThe bot may trade again if the strategy and safety checks allow it."
    if command in {"/sell", "/close"}:
        state = require_app_state(db, settings)
        trade = db.query(Trade).filter(Trade.symbol == state.active_symbol, Trade.status == "open").first()
        if trade is None:
            return "There is no open position for the active market."
        confirmation = create_confirmation(
            db,
            "close_position",
            {"trade_id": trade.id, "symbol": trade.symbol, "quantity": trade.quantity},
            requester_id=requester_id,
        )
        return (
            "Close position request\n"
            f"Market: {trade.symbol}\n"
            f"Quantity: {trade.quantity}\n\n"
            f"To close it, send: /confirm {confirmation.code}\n"
            "This code expires in 2 minutes."
        )
    if command == "/confirm":
        if len(parts) < 2:
            return "Send the code from /sell.\nExample: /confirm ABC123"
        payload = consume_confirmation(db, parts[1], "close_position", requester_id=requester_id)
        if payload is None:
            return "That confirmation code is invalid, expired, or from another chat.\nSend /sell to create a fresh code."
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
    return "I did not understand that.\nSend /menu to see what I can do."


def _normalize_command(raw: str) -> str:
    command = raw.lower()
    if command.startswith("/"):
        return command
    aliases = {
        "start": "/start",
        "menu": "/menu",
        "help": "/help",
        "status": "/status",
        "account": "/account",
        "symbols": "/symbols",
        "markets": "/markets",
        "risk": "/risk",
        "stop": "/stop",
        "resume": "/resume",
        "sell": "/sell",
        "close": "/close",
        "why": "/whyhold",
    }
    return aliases.get(command, command)


def _welcome_message() -> str:
    return (
        "Trader bot menu\n\n"
        "What you can do:\n"
        "/status - see what the bot is doing\n"
        "/account - see equity and free balance\n"
        "/symbols - see markets you can pick\n"
        "/set BTC/USDT:USDT - change market\n"
        "/risk - see risk settings\n"
        "/setrisk 1 50 100 2 - change risk settings\n"
        "/calc BTC/USDT:USDT 1 50 - preview position size\n"
        "/whyhold - explain the last HOLD\n"
        "/stop - pause trading\n"
        "/resume - allow trading again\n"
        "/sell - close an open position with confirmation\n\n"
        "Good first step: send /status"
    )


def _watchlist_message(items, active_symbol: str) -> str:
    if not items:
        return "Your watchlist is empty."
    grouped: dict[str, list[str]] = {}
    for item in items:
        marker = " selected" if item.symbol == active_symbol else ""
        grouped.setdefault(item.asset_class, []).append(f"- {item.symbol} ({item.provider}){marker}")
    lines = ["Markets"]
    for asset_class in sorted(grouped):
        lines.append("")
        lines.append(asset_class.title())
        lines.extend(grouped[asset_class][:12])
    lines.append("")
    lines.append("Change market with: /set SYMBOL")
    return "\n".join(lines)


def _money(value) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "0.00"


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
