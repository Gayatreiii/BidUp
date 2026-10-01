"""Supported stock universe (NSE). Edit here if a ticker changes on the exchange."""

_RAW = [
    ("TCS", "Tata Consultancy Services", "IT"), ("INFY", "Infosys", "IT"),
    ("WIPRO", "Wipro", "IT"), ("HCLTECH", "HCL Technologies", "IT"), ("TECHM", "Tech Mahindra", "IT"),
    ("HDFCBANK", "HDFC Bank", "Banking"), ("ICICIBANK", "ICICI Bank", "Banking"),
    ("SBIN", "State Bank of India", "Banking"), ("KOTAKBANK", "Kotak Mahindra Bank", "Banking"),
    ("AXISBANK", "Axis Bank", "Banking"),
    ("RELIANCE", "Reliance Industries", "Energy"), ("ONGC", "Oil and Natural Gas Corporation", "Energy"),
    ("BPCL", "Bharat Petroleum", "Energy"), ("IOC", "Indian Oil Corporation", "Energy"),
    ("COALINDIA", "Coal India", "Energy"),
    ("TATASTEEL", "Tata Steel", "Metals"), ("JSWSTEEL", "JSW Steel", "Metals"),
    ("HINDALCO", "Hindalco Industries", "Metals"), ("VEDL", "Vedanta", "Metals"), ("SAIL", "Steel Authority of India", "Metals"),
    ("MARUTI", "Maruti Suzuki", "Auto"), ("BAJAJ-AUTO", "Bajaj Auto", "Auto"),
    ("EICHERMOT", "Eicher Motors", "Auto"), ("HEROMOTOCO", "Hero MotoCorp", "Auto"),
    ("HINDUNILVR", "Hindustan Unilever", "FMCG"), ("ITC", "ITC", "FMCG"),
    ("NESTLEIND", "Nestle India", "FMCG"), ("BRITANNIA", "Britannia Industries", "FMCG"), ("DABUR", "Dabur India", "FMCG"),
    ("SUNPHARMA", "Sun Pharmaceutical", "Pharma"), ("DRREDDY", "Dr. Reddy's Laboratories", "Pharma"),
    ("CIPLA", "Cipla", "Pharma"), ("DIVISLAB", "Divi's Laboratories", "Pharma"),
    ("BHARTIARTL", "Bharti Airtel", "Telecom"), ("INDUSTOWER", "Indus Towers", "Telecom"),
    ("LT", "Larsen & Toubro", "Infra"), ("ADANIPORTS", "Adani Ports", "Infra"), ("ULTRACEMCO", "UltraTech Cement", "Infra"),
]

UNIVERSE = {t: {"name": n, "sector": s} for t, n, s in _RAW}
SECTORS = sorted({v["sector"] for v in UNIVERSE.values()})
CRUDE_NODE = "Crude Oil"      # external (non-equity) node in the risk graph
CRUDE_SYMBOL = "CL=F"
CRUDE_COLUMN = "CRUDE"

DEMO_PORTFOLIO = [
    {"ticker": "TCS", "quantity": 10, "avg_buy_price": 3500},
    {"ticker": "INFY", "quantity": 25, "avg_buy_price": 1500},
    {"ticker": "HDFCBANK", "quantity": 30, "avg_buy_price": 1600},
    {"ticker": "RELIANCE", "quantity": 20, "avg_buy_price": 2500},
    {"ticker": "ONGC", "quantity": 100, "avg_buy_price": 200},
    {"ticker": "TATASTEEL", "quantity": 150, "avg_buy_price": 120},
    {"ticker": "ITC", "quantity": 80, "avg_buy_price": 400},
]


import re as _re

EXTRA: dict = {}   # holdings outside the curated list, resolved via Yahoo (ticker = full Yahoo symbol e.g. RBA.NS)
_SYM_OK = _re.compile(r"^[A-Z0-9&\-\.\^=]{1,25}$")


def known(ticker: str) -> bool:
    return ticker in UNIVERSE or ticker in EXTRA


def info(ticker: str) -> dict:
    return UNIVERSE[ticker] if ticker in UNIVERSE else EXTRA[ticker]


def register_extra(ticker: str, name: str, sector: str) -> bool:
    t = str(ticker).upper()
    if t in UNIVERSE:
        return True
    if not _SYM_OK.match(t) or not t.endswith((".NS", ".BO")) or (t not in EXTRA and len(EXTRA) >= 500):
        return False
    EXTRA[t] = {"name": str(name)[:80], "sector": (str(sector)[:40] or "Other")}
    return True


def yahoo_symbol(ticker: str) -> str:
    return ticker if ticker in EXTRA else f"{ticker}.NS"
