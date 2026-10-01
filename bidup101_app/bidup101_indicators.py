"""Technical indicators (via the `ta` library) with plain-language, descriptive explanations."""
import math
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD
from ta.volatility import BollingerBands


def _clean(series: pd.Series):
    return [None if (v is None or (isinstance(v, float) and math.isnan(v))) else round(float(v), 2) for v in series]


def rsi_last(close: pd.Series):
    close = close.dropna()
    if len(close) < 20:
        return None
    v = RSIIndicator(close, window=14).rsi().iloc[-1]
    return None if math.isnan(v) else float(v)


def compute(close: pd.Series, points: int = 180) -> dict:
    close = close.dropna()
    if len(close) < 35:
        raise ValueError("Not enough price history to compute indicators.")
    rsi = RSIIndicator(close, window=14).rsi()
    macd = MACD(close)
    bb = BollingerBands(close, window=20, window_dev=2)
    r = float(rsi.iloc[-1])
    hist = float(macd.macd_diff().iloc[-1])
    price = float(close.iloc[-1])
    up, lo = float(bb.bollinger_hband().iloc[-1]), float(bb.bollinger_lband().iloc[-1])

    if r >= 70:
        rsi_txt = f"RSI is {r:.0f}. Values above 70 mean the price has risen quickly lately; this is commonly described as 'overbought'."
    elif r <= 30:
        rsi_txt = f"RSI is {r:.0f}. Values below 30 mean the price has fallen quickly lately; this is commonly described as 'oversold'."
    else:
        rsi_txt = f"RSI is {r:.0f}, in the middle range (30-70), so recent price momentum is neither unusually strong nor weak."
    macd_txt = ("MACD momentum is currently positive: the short-term average sits above the longer-term one."
                if hist > 0 else
                "MACD momentum is currently negative: the short-term average sits below the longer-term one.")
    if price >= up:
        bb_txt = "Price is at or above the upper Bollinger band, meaning it is unusually high versus its own last 20 days."
    elif price <= lo:
        bb_txt = "Price is at or below the lower Bollinger band, meaning it is unusually low versus its own last 20 days."
    else:
        bb_txt = "Price is inside its Bollinger bands, meaning it is within its normal recent range."

    sl = slice(-points, None)
    return {
        "rsi": round(r, 1), "macd_hist": round(hist, 3), "price": round(price, 2),
        "bb_upper": round(up, 2), "bb_lower": round(lo, 2),
        "explanations": {"RSI (Relative Strength Index)": rsi_txt,
                         "MACD (Moving Average Convergence Divergence)": macd_txt,
                         "Bollinger Bands": bb_txt},
        "chart": {"dates": [d.strftime("%Y-%m-%d") for d in close.index[sl]],
                  "close": _clean(close[sl]), "upper": _clean(bb.bollinger_hband()[sl]),
                  "lower": _clean(bb.bollinger_lband()[sl]), "sma": _clean(bb.bollinger_mavg()[sl])},
    }
