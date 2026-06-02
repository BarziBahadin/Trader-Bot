import pandas as pd

from app.strategy.indicators import add_indicators


def test_add_indicators_creates_expected_columns():
    df = pd.DataFrame({"close": list(range(1, 61))})

    result = add_indicators(df, rsi_period=14, fast_ma=20, slow_ma=50)

    assert {"rsi", "fast_ma", "slow_ma"}.issubset(result.columns)
    assert result["fast_ma"].iloc[-1] == sum(range(41, 61)) / 20
    assert result["slow_ma"].iloc[-1] == sum(range(11, 61)) / 50

