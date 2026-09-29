"""BidUp101 FastAPI application: JSON API + static frontend in a single deployable service."""
import threading
from contextlib import asynccontextmanager
import base64
from typing import List, Optional

from fastapi import APIRouter, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import bidup101_config as cfg
from . import bidup101_llm as llm
from . import bidup101_market as market
from . import bidup101_news as news
from . import bidup101_portfolio as pf
from . import bidup101_risk as risk
from . import bidup101_resolver as resolver
from . import bidup101_screener as screener
from . import bidup101_indicators as ind
from .bidup101_universe import UNIVERSE, DEMO_PORTFOLIO, register_extra


def _warm():
    try:
        market.get_history()
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app):
    threading.Thread(target=_warm, daemon=True).start()
    yield


bidup101_api = FastAPI(title="BidUp101", version="1.0.0", lifespan=lifespan)
router = APIRouter(prefix="/api/bidup101")


class HoldingIn(BaseModel):
    ticker: str
    quantity: float = Field(gt=0)
    avg_buy_price: float = Field(ge=0)
    name: Optional[str] = None      # only for holdings outside the curated list
    sector: Optional[str] = None
    symbol: Optional[str] = None


class PortfolioIn(BaseModel):
    holdings: List[HoldingIn]


class ImportIn(BaseModel):
    csv: Optional[str] = None          # CSV or pasted text
    pdf_base64: Optional[str] = None   # PDF statement, base64


class ResolveIn(BaseModel):
    query: str = Field(min_length=1, max_length=100)


class ChatIn(BaseModel):
    holdings: List[HoldingIn]
    message: str = Field(min_length=1, max_length=1500)
    history: List[dict] = []


class ScreenIn(BaseModel):
    query: str = Field(min_length=1, max_length=300)


class StockIn(BaseModel):
    holdings: List[HoldingIn] = []
    amount: float = Field(default=0, ge=0)


class ComparePortfolio(BaseModel):
    name: str
    holdings: List[HoldingIn]


class CompareIn(BaseModel):
    portfolios: List[ComparePortfolio] = Field(min_length=2, max_length=4)


def _clean(hs):
    out = []
    for h in hs:
        t = h.ticker.upper()
        if t not in UNIVERSE and not (h.name and h.sector and register_extra(t, h.name, h.sector)):
            continue
        out.append(h.model_dump() | {"ticker": t})
    return out


def _overview(holdings: list) -> dict:
    if not holdings:
        raise HTTPException(400, "Portfolio is empty.")
    try:
        quotes = market.get_quotes([h["ticker"] for h in holdings])
        port = pf.analyze(holdings, quotes)
        try:
            rk = risk.assess(market.get_history(), port["sector_weights"])
        except Exception as e:
            rk = {"error": f"Risk model unavailable: {e}", "alerts": [], "nodes": [], "edges": [],
                  "disclosure": "Risk model could not run."}
        return {"portfolio": port, "risk": rk, "market": market.status()}
    except market.MarketDataError as e:
        raise HTTPException(503, str(e))


@router.get("/health")
def health():
    return {"status": "ok", "llm_configured": bool(cfg.env("NEMOTRON_API_KEY")),
            "news_configured": bool(cfg.env("NEWSDATA_API_KEY")), "gat_trained": risk.gat.get_model().trained}


@router.get("/universe")
def universe():
    return [{"ticker": t, **v} for t, v in UNIVERSE.items()]


@router.get("/demo")
def demo():
    return DEMO_PORTFOLIO


@router.post("/portfolio/import")
def import_any(body: ImportIn):
    text = body.csv
    if body.pdf_base64:
        try:
            raw = base64.b64decode(body.pdf_base64)
            if len(raw) > 8 * 1024 * 1024:
                return {"ok": False, "error": "PDF is larger than 8 MB.", "holdings": [], "unresolved": []}
            text = pf.pdf_to_text(raw)
        except ValueError as e:
            return {"ok": False, "error": str(e), "holdings": [], "unresolved": []}
        except Exception:
            return {"ok": False, "error": "Couldn't read this PDF. Export the statement as CSV instead, or add holdings manually.",
                    "holdings": [], "unresolved": []}
    return pf.parse_any(text or "", resolver.resolve_many)


@router.post("/portfolio/resolve")
def resolve(body: ResolveIn):
    r = resolver.resolve_one(body.query)
    if not r:
        return {"ok": False, "error": f"Couldn't find a listed NSE/BSE stock matching '{body.query}'. "
                                      "Try the full company name or the exchange ticker."}
    return {"ok": True, **r}


@router.post("/overview")
def overview(body: PortfolioIn):
    return _overview(_clean(body.holdings))


@router.post("/news")
def portfolio_news(body: PortfolioIn):
    return news.portfolio_news(_clean(body.holdings))


@router.post("/chat")
def chat(body: ChatIn):
    holdings = _clean(body.holdings)
    if not holdings:
        raise HTTPException(400, "Portfolio is empty.")
    ov = _overview(holdings)
    p, r = ov["portfolio"], ov["risk"]
    ctx = (f"Holdings: {p['num_holdings']} across {p['num_sectors']} sectors. Total value Rs {p['total_value']:,.0f}. "
           f"Concentration: {p['band']['label']} (HHI {p['hhi']}). Sector weights: "
           + ", ".join(f"{k} {v*100:.0f}%" for k, v in p["sector_weights"].items()) + ". "
           + "Holdings detail: " + "; ".join(f"{h['ticker']} ({h['sector']}) {h['weight']*100:.0f}%" for h in p["holdings"]) + ". "
           + "Active risk signals: " + (" | ".join(a["text"] for a in r["alerts"]) or "none") + ". "
           + f"Risk model: {r.get('method', 'n/a')}.")
    try:
        return {"ok": True, **llm.chat_answer(body.message, body.history, ctx)}
    except llm.LLMError:
        return {"ok": False, "error": "AI temporarily unavailable — please retry"}


@router.post("/screener")
def screen(body: ScreenIn):
    try:
        return screener.run(body.query)
    except market.MarketDataError as e:
        raise HTTPException(503, str(e))


@router.post("/stock/{ticker}")
def stock(ticker: str, body: StockIn):
    t = ticker.upper()
    if t not in UNIVERSE:
        raise HTTPException(404, f"Unknown ticker: {ticker}")
    try:
        hist = market.get_history()
        if t not in hist:
            raise HTTPException(503, "No price data for this ticker right now.")
        indicators = ind.compute(hist[t])
        quote = market.get_quotes([t]).get(t)
    except market.MarketDataError as e:
        raise HTTPException(503, str(e))
    impact = None
    holdings = _clean(body.holdings)
    if holdings and body.amount > 0:
        port = pf.analyze(holdings, market.get_quotes([h["ticker"] for h in holdings]))
        impact = pf.simulate_addition(port, t, body.amount)
    return {"ticker": t, **UNIVERSE[t], "quote": quote, "indicators": indicators, "impact": impact,
            "news": news.ticker_news(t)}


@router.post("/compare")
def compare(body: CompareIn):
    out = []
    for p in body.portfolios:
        ov = _overview(_clean(p.holdings))
        out.append({"name": p.name, **ov})
    return out


@router.get("/methodology")
def methodology():
    if cfg.METHODOLOGY_FILE.exists():
        return {"markdown": cfg.METHODOLOGY_FILE.read_text(encoding="utf-8")}
    return {"markdown": "Methodology file not found."}


bidup101_api.include_router(router)


@bidup101_api.exception_handler(Exception)
async def _unhandled(_, exc):
    return JSONResponse({"detail": "Unexpected server error."}, status_code=500)


@bidup101_api.get("/")
def index():
    return FileResponse(cfg.WEB_DIR / "bidup101_index.html")


bidup101_api.mount("/static", StaticFiles(directory=cfg.WEB_DIR), name="bidup101_static")
