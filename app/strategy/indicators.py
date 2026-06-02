import pandas as pd


def moving_average(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def add_indicators(df: pd.DataFrame, rsi_period: int, fast_ma: int, slow_ma: int) -> pd.DataFrame:
    result = df.copy()
    result["rsi"] = rsi(result["close"], rsi_period)
    result["fast_ma"] = moving_average(result["close"], fast_ma)
    result["slow_ma"] = moving_average(result["close"], slow_ma)
    return result

