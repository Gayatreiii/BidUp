"""Resolve company names outside the curated list to NSE/BSE symbols via Yahoo Finance search.

Matches are name-checked (not blindly trusted) and always shown to the user for confirmation.
"""
from concurrent.futures import ThreadPoolExecutor
import yfinance as yf

from . import bidup101_universe as U
from .bidup101_portfolio import _norm_name, _resolve

_cache: dict = {}


def _toks(s: str):
    return _norm_name(s).split()


def _hit(t: str, others) -> bool:
    return any(c == t or (len(t) >= 4 and c.startswith(t)) for c in others)


def _score(query: str, cand: str) -> float:
    qt, ct = _toks(query), _toks(cand)
    if not qt or not ct:
        return 0.0
    qh = sum(1 for t in qt if _hit(t, ct)) / len(qt)      # how much of the broker's name is explained
    ch = sum(1 for c in ct if _hit(c, qt)) / len(ct)      # how much of Yahoo's name is explained
    return (qh + ch) / 2 if qh >= 0.75 and ch >= 0.5 else 0.0


def _sector(sym: str) -> str:
    """Map Yahoo sector/industry onto BidUp101's sector names (the 9 risk-model sectors when they fit)."""
    try:
        inf = yf.Ticker(sym).info or {}
    except Exception:
        return "Other"
    sec, ind = inf.get("sector") or "", (inf.get("industry") or "").lower()
    has = lambda *w: any(x in ind for x in w)
    if sec == "Technology":
        return "IT"
    if sec == "Financial Services":
        return "Banking" if has("bank") else "Financial Services"
    if sec == "Energy":
        return "Energy"
    if sec == "Basic Materials":
        return "Metals" if has("steel", "alumin", "copper", "metal", "gold", "silver", "mining", "zinc") else "Materials"
    if sec == "Healthcare":
        return "Pharma" if has("drug", "pharma", "biotech") else "Healthcare"
    if sec == "Consumer Defensive":
        return "FMCG"
    if sec == "Consumer Cyclical":
        return "Auto" if has("auto") else "Consumer Cyclical"
    if sec == "Communication Services":
        return "Telecom" if has("telecom") else "Communication Services"
    if sec == "Industrials":
        return "Infra" if has("engineering", "infrastructure", "construction", "building", "port", "cement") else "Industrials"
    return sec or "Other"


def resolve_one(query: str):
    q = (query or "").strip()
    if not q:
        return None
    t = _resolve(q)                      # curated list first (exact ticker / known name)
    if t:
        return {"ticker": t, "name": U.UNIVERSE[t]["name"], "sector": U.UNIVERSE[t]["sector"], "curated": True}
    key = _norm_name(q)
    if key in _cache:
        return _cache[key]
    try:
        quotes = yf.Search(q, max_results=10).quotes or []
    except Exception:
        return None
    best, best_sc = None, 0.0
    for r in quotes:
        sym = (r.get("symbol") or "").upper()
        if not sym.endswith((".NS", ".BO")) or r.get("quoteType", "EQUITY") != "EQUITY":
            continue
        sc = 1.0 if sym.rsplit(".", 1)[0] == q.upper() else _score(q, r.get("longname") or r.get("shortname") or "")
        if sc and sym.endswith(".NS"):
            sc += 0.05                     # prefer NSE listing when both exist
        if sc > best_sc:
            best, best_sc = r, sc
    if not best:
        return None
    sym = best["symbol"].upper()
    base = sym.rsplit(".", 1)[0]
    if base in U.UNIVERSE:
        out = {"ticker": base, "name": U.UNIVERSE[base]["name"], "sector": U.UNIVERSE[base]["sector"], "curated": True}
    else:
        out = {"ticker": sym, "name": best.get("longname") or best.get("shortname") or sym, "sector": _sector(sym)}
    _cache[key] = out
    return out


def resolve_many(names):
    with ThreadPoolExecutor(max_workers=5) as ex:
        return dict(zip(names, ex.map(resolve_one, names)))
