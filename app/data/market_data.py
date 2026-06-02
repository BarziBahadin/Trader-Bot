import pandas as pd

from app.exchange.base import ExchangeClient


OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


class MarketData:
    def __init__(self, exchange: ExchangeClient):
        self.exchange = exchange

    def candles(self, symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
        rows = self.exchange.fetch_ohlcv(symbol, timeframe, limit)
        df = pd.DataFrame(rows, columns=OHLCV_COLUMNS)
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df

    @staticmethod
    def from_csv(path: str) -> pd.DataFrame:
        df = pd.read_csv(path)
        missing = set(OHLCV_COLUMNS) - set(df.columns)
        if missing:
            raise ValueError(f"CSV missing OHLCV columns: {sorted(missing)}")
        return df

