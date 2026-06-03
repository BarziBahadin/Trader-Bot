from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


BotMode = Literal["paper", "testnet", "live", "backtest"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_mode: BotMode = Field(default="paper", alias="BOT_MODE")
    enable_real_trading: bool = Field(default=False, alias="ENABLE_REAL_TRADING")

    exchange: str = Field(default="okx", alias="EXCHANGE")
    provider: str = Field(default="paper", alias="PROVIDER")
    symbol: str = Field(default="BTC/USDT", alias="SYMBOL")
    timeframe: str = Field(default="15m", alias="TIMEFRAME")
    asset_class: str = Field(default="crypto", alias="ASSET_CLASS")

    okx_api_key: str = Field(default="", alias="OKX_API_KEY")
    okx_api_secret: str = Field(default="", alias="OKX_API_SECRET")
    okx_passphrase: str = Field(default="", alias="OKX_PASSPHRASE")
    okx_demo: bool = Field(default=True, alias="OKX_DEMO")
    okx_market_type: str = Field(default="swap", alias="OKX_MARKET_TYPE")
    okx_margin_mode: str = Field(default="cross", alias="OKX_MARGIN_MODE")
    live_trading_ack: str = Field(default="", alias="LIVE_TRADING_ACK")
    api_auth_token: str = Field(default="", alias="API_AUTH_TOKEN")
    cors_origins: str = Field(default="http://127.0.0.1:5173,http://localhost:5173", alias="CORS_ORIGINS")

    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")

    initial_balance: float = Field(default=10_000.0, alias="INITIAL_BALANCE", gt=0)
    account_currency: str = Field(default="USDT", alias="ACCOUNT_CURRENCY")
    default_leverage: float = Field(default=1.0, alias="DEFAULT_LEVERAGE", gt=0)
    default_lot_size: float = Field(default=0.01, alias="DEFAULT_LOT_SIZE", gt=0)
    max_leverage: float = Field(default=3.0, alias="MAX_LEVERAGE", gt=0)
    max_position_notional: float = Field(default=100.0, alias="MAX_POSITION_NOTIONAL", gt=0)
    auto_start_worker: bool = Field(default=True, alias="AUTO_START_WORKER")
    auto_start_telegram: bool = Field(default=True, alias="AUTO_START_TELEGRAM")
    load_provider_symbols_on_startup: bool = Field(default=False, alias="LOAD_PROVIDER_SYMBOLS_ON_STARTUP")
    risk_per_trade: float = Field(default=0.01, alias="RISK_PER_TRADE", gt=0, le=0.05)
    max_daily_loss: float = Field(default=0.03, alias="MAX_DAILY_LOSS", gt=0, le=0.25)
    stop_loss_percent: float = Field(default=0.01, alias="STOP_LOSS_PERCENT", gt=0)
    take_profit_percent: float = Field(default=0.02, alias="TAKE_PROFIT_PERCENT", gt=0)

    rsi_period: int = Field(default=14, alias="RSI_PERIOD", ge=2)
    rsi_buy_level: float = Field(default=30, alias="RSI_BUY_LEVEL", ge=1, le=100)
    rsi_sell_level: float = Field(default=70, alias="RSI_SELL_LEVEL", ge=1, le=100)
    fast_ma: int = Field(default=20, alias="FAST_MA", ge=2)
    slow_ma: int = Field(default=50, alias="SLOW_MA", ge=3)

    database_url: str = Field(default="sqlite:///./trading_bot.db", alias="DATABASE_URL")
    stop_file: Path = Field(default=Path("STOP_BOT.txt"), alias="STOP_FILE")

    @field_validator("bot_mode")
    @classmethod
    def normalize_mode(cls, value: str) -> str:
        return value.lower()

    @field_validator("slow_ma")
    @classmethod
    def slow_ma_must_exceed_fast_ma(cls, value: int, info):
        fast_ma = info.data.get("fast_ma")
        if fast_ma and value <= fast_ma:
            raise ValueError("SLOW_MA must be greater than FAST_MA")
        return value

    @property
    def is_live_trading_allowed(self) -> bool:
        return self.bot_mode == "live" and self.enable_real_trading

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
