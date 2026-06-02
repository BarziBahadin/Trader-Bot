import requests
from loguru import logger


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send(self, message: str) -> None:
        if not self.enabled:
            return
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            response = requests.post(url, json={"chat_id": self.chat_id, "text": message}, timeout=10)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Telegram alert failed: {}", exc)

