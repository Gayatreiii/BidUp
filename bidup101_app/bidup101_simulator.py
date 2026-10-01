"""Portfolio Simulator: add hypothetical stocks to an existing portfolio (or simulate standalone) and
see historical performance and the resulting Portfolio Health (HHI band) versus the current portfolio.
Reuses bidup101_portfolio.analyze for the health score so the numbers match the rest of the app exactly.
"""
import numpy as np
import pandas as pd

from . import bidup101_market as market
from . import bidup101_portfolio as pf
from .bidup101_universe import known, yahoo_symbol

PERIODS = {"3m": "3mo", "6m": "6mo", "1y": "1y", "3y": "3y"}


def _closes(tickers: list, period: str) -> pd.DataFrame:
    tickers = [t for t in dict.fromkeys(tickers) if known(t)]
    if not tickers:
        return pd.DataFrame()
    sym_map = {yahoo_symbol(t): t for t in tickers}
    close = market.download_close(list(sym_map), period).rename(columns=sym_map)
    return close.ffill().dropna(how="all")


def _series_value(close: pd.DataFrame, holdings: list) -> pd.Series:
    """Daily portfolio value: quantity held is fixed at latest known quantity (no rebalancing)."""
    val = None
    for h in holdings:
        t = h["ticker"]
        if t not in close.columns:
            continue
        s = close[t].dropna() * h["quantity"]
        val = s if val is None else val.add(s, fill_value=0)
    return val if val is not None else pd.Series(dtype=float)


def run(base_holdings: list, additions: list, period_key: str = "1y") -> dict:
    """additions: list of {ticker, quantity, avg_buy_price(optional, for cost basis only)}"""
    period = PERIODS.get(period_key, "1y")
    base_holdings = [h for h in base_holdings if known(h["ticker"])]
    additions = [h for h in additions if known(h["ticker"])]
    if not base_holdings and not additions:
        raise ValueError("Add at least one holding (existing or new) to simulate.")

    all_tickers = [h["ticker"] for h in base_holdings] + [h["ticker"] for h in additions]
    close = _closes(all_tickers, period)
    if close.empty:
        raise ValueError("No price history available for the selected stocks.")

    base_val = _series_value(close, base_holdings) if base_holdings else pd.Series(0.0, index=close.index)
    combined_val = _series_value(close, base_holdings + additions)
    idx = combined_val.dropna().index
    if len(idx) < 2:
        raise ValueError("Not enough overlapping price history for these stocks.")
    base_val = base_val.reindex(idx).ffill().fillna(0.0)
    combined_val = combined_val.reindex(idx)

    def normalize(s: pd.Series):
        first = next((v for v in s.values if v and v > 0), None)
        if not first:
            return [0.0] * len(s)
        return [round(float(v / first - 1) * 100, 2) for v in s.values]

    quotes = market.get_quotes(all_tickers)
    base_health = pf.analyze(base_holdings, quotes) if base_holdings else None
    combined_health = pf.analyze(base_holdings + additions, quotes)

    total_return = lambda s: round(float(s.iloc[-1] / s.iloc[0] - 1) * 100, 2) if s.iloc[0] else 0.0
    daily = combined_val.pct_change().dropna()
    volatility_pct = round(float(daily.std() * np.sqrt(252) * 100), 2) if len(daily) > 5 else None
    peak = combined_val.cummax()
    max_drawdown_pct = round(float(((combined_val - peak) / peak).min() * 100), 2) if len(peak) else None

    return {
        "dates": [d.strftime("%Y-%m-%d") for d in idx],
        "base_pct": normalize(base_val) if base_holdings else None,
        "combined_pct": normalize(combined_val),
        "base_total_return_pct": total_return(base_val) if base_holdings else None,
        "combined_total_return_pct": total_return(combined_val),
        "volatility_pct": volatility_pct,
        "max_drawdown_pct": max_drawdown_pct,
        "base_health": None if base_health is None else {
            "band": base_health["band"], "hhi": base_health["hhi"], "total_value": base_health["total_value"]},
        "combined_health": {
            "band": combined_health["band"], "hhi": combined_health["hhi"],
            "total_value": combined_health["total_value"], "sector_weights": combined_health["sector_weights"]},
        "note": "Simulation assumes today's share count held unchanged across the whole period (no rebalancing, dividends excluded). Not a prediction — for education only.",
    }
