"""Market data via yfinance with caching. Data is delayed (~15 min), never claimed real-time."""
import threading
import time
import datetime as dt
import pandas as pd
import yfinance as yf

from . import bidup101_config as cfg
from .bidup101_universe import UNIVERSE, CRUDE_SYMBOL, CRUDE_COLUMN, yahoo_symbol, known


class MarketDataError(Exception):
    pass


_lock = threading.Lock()
_hist = {"df": None, "ts": 0.0, "as_of": None}
_quotes: dict = {}
_status = {"history_error": None, "quote_error": None}


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def download_close(symbols, period: str) -> pd.DataFrame:
    raw = yf.download(symbols, period=period, interval="1d", auto_adjust=True,
                      progress=False, threads=True)
    if raw is None or len(raw) == 0:
        raise MarketDataError("empty response from data provider")
    close = raw["Close"] if "Close" in raw else raw
    if isinstance(close, pd.Series):
        close = close.to_frame(symbols[0])
    return close


def download_history(period: str = "1y") -> pd.DataFrame:
    """Daily closes for whole universe + crude oil, columns = NSE ticker (+ CRUDE)."""
    sym_map = {yahoo_symbol(t): t for t in UNIVERSE}
    sym_map[CRUDE_SYMBOL] = CRUDE_COLUMN
    close = download_close(list(sym_map), period).rename(columns=sym_map)
    close = close.dropna(axis=1, how="all").ffill().dropna(how="all")
    if close.shape[1] < 5:
        raise MarketDataError("too few instruments returned")
    return close


def get_history(force: bool = False) -> pd.DataFrame:
    with _lock:
        fresh = _hist["df"] is not None and (time.time() - _hist["ts"]) < cfg.HISTORY_TTL_SEC
        if fresh and not force:
            return _hist["df"]
        try:
            df = download_history("1y")
            _hist.update(df=df, ts=time.time(), as_of=_now_iso())
            _status["history_error"] = None
        except Exception as e:  # keep last good data
            _status["history_error"] = str(e)[:200]
            if _hist["df"] is None:
                raise MarketDataError(f"Market data unavailable: {e}") from e
        return _hist["df"]


def history_version() -> float:
    return _hist["ts"]


def get_quotes(tickers) -> dict:
    """Latest known price per ticker with an as_of timestamp. Falls back to last good value."""
    now = time.time()
    need = [t for t in tickers if known(t) and
            (t not in _quotes or now - _quotes[t]["fetched"] > cfg.QUOTE_TTL_SEC)]
    if need:
        try:
            close = download_close([yahoo_symbol(t) for t in need], "5d")
            for t in need:
                col = yahoo_symbol(t)
                if col in close:
                    s = close[col].dropna()
                    if len(s):
                        price = float(s.iloc[-1])
                        prev = float(s.iloc[-2]) if len(s) > 1 else price
                        _quotes[t] = {"price": price, "prev_close": prev,
                                      "change_pct": (price / prev - 1) * 100 if prev else 0.0,
                                      "as_of": _now_iso(), "fetched": now, "stale": False}
            _status["quote_error"] = None
        except Exception as e:
            _status["quote_error"] = str(e)[:200]
            for t in need:  # mark existing values stale rather than blanking them
                if t in _quotes:
                    _quotes[t]["stale"] = True
    out = {}
    for t in tickers:
        if not known(t):
            continue
        q = _quotes.get(t)
        if q is None:
            try:
                s = get_history()[t].dropna()
                prev = float(s.iloc[-2]) if len(s) > 1 else float(s.iloc[-1])
                q = {"price": float(s.iloc[-1]), "prev_close": prev,
                     "change_pct": (float(s.iloc[-1]) / prev - 1) * 100 if prev else 0.0,
                     "as_of": pd.Timestamp(s.index[-1]).tz_localize("UTC").isoformat()
                     if pd.Timestamp(s.index[-1]).tzinfo is None else pd.Timestamp(s.index[-1]).isoformat(),
                     "fetched": 0, "stale": True}
            except Exception:
                continue
        out[t] = {k: v for k, v in q.items() if k != "fetched"}
    return out


def status() -> dict:
    return {"history_as_of": _hist["as_of"], "history_error": _status["history_error"],
            "quote_error": _status["quote_error"],
            "note": "Prices come from Yahoo Finance via yfinance and are typically ~15 minutes delayed."}
