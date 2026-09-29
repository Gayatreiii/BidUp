"""News via NewsData.io: real article links, real pubDate timestamps, cached per ticker, sentiment tagged."""
import json
import re
import threading
import time
import datetime as dt
import requests

from . import bidup101_config as cfg
from . import bidup101_llm as llm
from .bidup101_universe import info

_cache: dict = {}
_lock = threading.Lock()
_POS = {"surge", "gain", "gains", "rise", "rises", "rally", "profit", "beat", "beats", "growth", "upgrade", "record",
        "jump", "jumps", "strong", "wins", "win", "order", "soar", "soars", "boost", "rebound"}
_NEG = {"fall", "falls", "drop", "drops", "plunge", "plunges", "loss", "losses", "miss", "misses", "downgrade",
        "probe", "fraud", "slump", "weak", "decline", "declines", "cut", "cuts", "penalty", "crash", "tumble", "slide"}


def _lexicon(title: str) -> str:
    words = set(re.findall(r"[a-z]+", title.lower()))
    s = len(words & _POS) - len(words & _NEG)
    return "Bullish" if s > 0 else "Bearish" if s < 0 else "Neutral"


def _label_sentiment(titles: list):
    """LLM sentiment for a batch of headlines; falls back to a simple lexicon."""
    if not titles:
        return [], "none"
    try:
        prompt = ("Classify each Indian stock-market headline's likely sentiment for the named company as exactly one of "
                  "Bullish, Bearish, Neutral. Reply ONLY with a JSON array of strings, same order.\n" +
                  "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles)))
        out = llm.complete([{"role": "user", "content": prompt}], max_tokens=200, temperature=0)
        arr = json.loads(re.search(r"\[.*\]", out, re.S).group(0))
        if len(arr) == len(titles) and all(a in ("Bullish", "Bearish", "Neutral") for a in arr):
            return arr, "llm"
    except Exception:
        pass
    return [_lexicon(t) for t in titles], "lexicon"


def _iso(pub: str):
    if not pub:
        return None
    try:
        return dt.datetime.strptime(pub[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc).isoformat()
    except ValueError:
        return None


def _fetch(query: str, cache_key: str, ticker=None) -> dict:
    now = time.time()
    with _lock:
        c = _cache.get(cache_key)
        if c and now - c["ts"] < cfg.NEWS_TTL_SEC:
            return c
    key = cfg.env("NEWSDATA_API_KEY")
    if not key:
        return {"items": [], "error": "NEWSDATA_API_KEY is not configured", "ts": now}
    try:
        r = requests.get("https://newsdata.io/api/1/latest",
                         params={"apikey": key, "q": query[:100], "country": "in", "language": "en"}, timeout=20)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        results = r.json().get("results") or []
    except Exception as e:
        with _lock:
            if cache_key in _cache:  # serve last good copy on failure / rate limit
                return {**_cache[cache_key], "error": f"Showing cached news ({type(e).__name__})"}
        return {"items": [], "error": f"News temporarily unavailable ({type(e).__name__})", "ts": now}
    seen, raw = set(), []
    for a in results:
        title = (a.get("title") or "").strip()
        if not title or title in seen:
            continue
        seen.add(title)
        raw.append(a)
    raw = raw[:6]
    labels, method = _label_sentiment([a["title"] for a in raw])
    items = [{"title": a["title"], "link": a.get("link") or None, "source": a.get("source_name") or a.get("source_id"),
              "published_at": _iso(a.get("pubDate")), "sentiment": labels[i], "sentiment_method": method,
              "ticker": ticker} for i, a in enumerate(raw)]
    entry = {"items": items, "error": None, "ts": now}
    with _lock:
        _cache[cache_key] = entry
    return entry


def ticker_news(ticker: str) -> dict:
    name = info(ticker)["name"]
    return _fetch(f'"{name}"', f"t:{ticker}", ticker)


def portfolio_news(holdings: list) -> dict:
    top = sorted(holdings, key=lambda h: -h["quantity"] * h["avg_buy_price"])[:5]
    items, errors = [], []
    for h in top:
        res = ticker_news(h["ticker"])
        items += res["items"]
        if res.get("error"):
            errors.append(res["error"])
    label = "Portfolio News"
    if not items:
        res = _fetch("Indian stock market NSE Sensex Nifty", "market", None)
        items, label = res["items"], "Market News"
        if res.get("error"):
            errors.append(res["error"])
    seen, out = set(), []
    for it in items:
        if it["title"] not in seen:
            seen.add(it["title"])
            out.append(it)
    out.sort(key=lambda x: x["published_at"] or "", reverse=True)
    note = None
    if label == "Market News":
        note = "No holding-specific articles were found, so general market news is shown instead."
    return {"label": label, "items": out[:15], "note": note, "errors": sorted(set(errors))}
