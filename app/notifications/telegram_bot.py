from __future__ import annotations

import os
import time

import requests

from app.config import Settings
from app.db.database import SessionLocal
from app.notifications.telegram import TelegramNotifier
from app.notifications.telegram_commands import handle_telegram_command
from app.utils.logger import logger


def run_telegram_polling(settings: Settings, interval_seconds: int = 3) -> None:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.info("Telegram polling disabled; token/chat id missing")
        return
    notifier = TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)
    offset = 0
    conflict_logged = False
    _set_bot_commands(settings)
    _delete_webhook(settings)
    while True:
        try:
            response = requests.get(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates",
                params={"offset": offset, "timeout": 20},
                timeout=30,
            )
            if response.status_code == 409:
                if not conflict_logged:
                    logger.warning(
                        "Telegram polling conflict: another process is already polling this bot token. "
                        "Stop the other backend or set AUTO_START_TELEGRAM=false there."
                    )
                    conflict_logged = True
                time.sleep(int(os.getenv("TELEGRAM_CONFLICT_BACKOFF_SECONDS", "60")))
                continue
            response.raise_for_status()
            conflict_logged = False
            for update in response.json().get("result", []):
                offset = max(offset, update["update_id"] + 1)
                message = update.get("message") or {}
                chat = message.get("chat") or {}
                if str(chat.get("id")) != str(settings.telegram_chat_id):
                    continue
                text = message.get("text", "")
                with SessionLocal() as db:
                    reply = handle_telegram_command(text, db, settings, requester_id=str(chat.get("id")))
                notifier.send(reply)
        except Exception as exc:
            logger.warning("Telegram polling failed: {}", _safe_telegram_error(exc))
            time.sleep(interval_seconds)


def _delete_webhook(settings: Settings) -> None:
    try:
        requests.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/deleteWebhook",
            json={"drop_pending_updates": False},
            timeout=10,
        )
    except requests.RequestException as exc:
        logger.warning("Telegram webhook cleanup failed: {}", _safe_telegram_error(exc))


def _set_bot_commands(settings: Settings) -> None:
    commands = [
        {"command": "start", "description": "Show the bot menu"},
        {"command": "status", "description": "Current bot status"},
        {"command": "account", "description": "Equity, balance, and PnL"},
        {"command": "symbols", "description": "Show market watchlist"},
        {"command": "set", "description": "Change active market"},
        {"command": "risk", "description": "Show risk settings"},
        {"command": "setrisk", "description": "Change risk settings"},
        {"command": "calc", "description": "Preview position size"},
        {"command": "whyhold", "description": "Explain the last hold"},
        {"command": "livecheck", "description": "Show live trading safety checks"},
        {"command": "stop", "description": "Emergency stop"},
        {"command": "resume", "description": "Resume trading"},
        {"command": "sell", "description": "Close position with confirmation"},
    ]
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/setMyCommands",
            json={"commands": commands},
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Telegram command menu setup failed: {}", _safe_telegram_error(exc))


def _safe_telegram_error(exc: Exception) -> str:
    return exc.__class__.__name__
