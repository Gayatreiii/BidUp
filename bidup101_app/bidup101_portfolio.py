"""CSV import/validation, valuation, HHI diversification analysis, what-if simulation."""
import csv
import io
from collections import defaultdict

import re

from .bidup101_universe import UNIVERSE, info

REQUIRED = ["ticker", "quantity", "avg_buy_price"]
HHI_EXPLAIN = ("HHI (Herfindahl-Hirschman Index) is a 0-10,000 score of concentration: "
               "the closer to 10,000, the more of your money sits in fewer sectors.")

# Column-name aliases (normalised: lowercase, letters/digits only, single spaces). Broker exports vary a lot.
_COL_ALIASES = {
    "ticker": {"ticker", "symbol", "stock name", "stock", "stock symbol", "instrument", "scrip", "scrip name",
               "company", "company name", "security", "security name", "name of stock", "trading symbol"},
    "quantity": {"quantity", "qty", "shares", "no of shares", "net qty", "net quantity", "holding qty",
                 "holding quantity", "quantity available", "total quantity"},
    "avg_buy_price": {"avg buy price", "average buy price", "avg price", "average price", "avg cost",
                      "average cost", "avg cost price", "average cost price", "buy avg", "buy average",
                      "avg buy", "avg trading price", "average price inr", "avg buy price inr", "avg buy price rs"},
}
_NAME_NOISE = {"LTD", "LIMITED", "CORPORATION", "CORP", "CO", "THE"}
_EXTRA_NAMES = {  # broker spellings that differ from the official short name
    "INFOSYS": "INFY", "MARUTI SUZUKI INDIA": "MARUTI", "SUN PHARMACEUTICAL INDUSTRIES": "SUNPHARMA",
    "ADANI PORTS AND SPECIAL ECONOMIC ZONE": "ADANIPORTS", "ADANI PORTS & SEZ": "ADANIPORTS",
    "DIVIS LABORATORIES": "DIVISLAB", "TATA CONSULTANCY SERVICES": "TCS", "HERO MOTOCORP": "HEROMOTOCO",
    "HINDUSTAN UNILEVER": "HINDUNILVR", "BAJAJ AUTO": "BAJAJ-AUTO", "INDUS TOWERS": "INDUSTOWER",
    "ULTRATECH CEMENT": "ULTRACEMCO", "BHARTI AIRTEL": "BHARTIARTL", "COAL INDIA": "COALINDIA",
    "HINDALCO INDUSTRIES": "HINDALCO", "VEDANTA": "VEDL", "EICHER MOTORS": "EICHERMOT",
    "STEEL AUTHORITY OF INDIA": "SAIL", "KOTAK MAHINDRA BANK": "KOTAKBANK", "LARSEN & TOUBRO": "LT",
    "STATE BANK OF INDIA": "SBIN", "TATA STEEL": "TATASTEEL", "JSW STEEL": "JSWSTEEL", "HDFC BANK": "HDFCBANK",
    "ICICI BANK": "ICICIBANK", "AXIS BANK": "AXISBANK", "HCL TECHNOLOGIES": "HCLTECH", "TECH MAHINDRA": "TECHM",
    "RELIANCE INDUSTRIES": "RELIANCE", "NESTLE INDIA": "NESTLEIND", "BRITANNIA INDUSTRIES": "BRITANNIA",
    "DABUR INDIA": "DABUR", "DR REDDYS LABORATORIES": "DRREDDY", "OIL AND NATURAL GAS CORPORATION": "ONGC",
    "BHARAT PETROLEUM CORPORATION": "BPCL", "INDIAN OIL CORPORATION": "IOC", "ADANI PORTS": "ADANIPORTS",
}
_name_index = None


def _norm_col(h: str) -> str:
    return " ".join("".join(c if c.isalnum() else " " for c in h.lower()).split())


def _norm_name(n: str) -> str:
    n = n.upper().replace("&", " AND ").replace("'", "").replace("\u2019", "")
    words = "".join(c if c.isalnum() else " " for c in n).split()
    return " ".join(w for w in words if w not in _NAME_NOISE)


def _resolve(raw: str):
    """Map a ticker OR a company name (as brokers export it) to a supported ticker, else None."""
    global _name_index
    if _name_index is None:
        _name_index = {}
        for t, u in UNIVERSE.items():
            _name_index[_norm_name(u["name"])] = t
        for nm, t in _EXTRA_NAMES.items():
            _name_index.setdefault(_norm_name(nm), t)
    t = raw.strip().upper()
    for pre in ("NSE:", "BSE:"):
        if t.startswith(pre):
            t = t[len(pre):]
    for suf in (".NS", ".BO", "-EQ", ".NSE"):
        if t.endswith(suf):
            t = t[: -len(suf)]
    if t in UNIVERSE:
        return t
    return _name_index.get(_norm_name(raw))


MAX_LOOKUPS = 15


def _fail(msg: str, kind: str = "invalid", **extra) -> dict:
    return {"ok": False, "error": msg, "kind": kind, "holdings": [], "unresolved": [], **extra}


def _n(x: str) -> float:
    return float(x.replace(",", "").replace("\u20b9", "").replace("Rs.", "").replace("Rs", "").replace("INR", "").strip())


def _find_table(rows):
    """Broker files start with account info; find the row that holds the real column headers."""
    best = (0, None, {})
    for i, r in enumerate(rows[:60]):
        found = {}
        for j, cell in enumerate(r):
            n = _norm_col(cell)
            for key, aliases in _COL_ALIASES.items():
                if n in aliases and key not in found:
                    found[key] = j
        if len(found) > best[0]:
            best = (len(found), i, found)
        if len(found) == 3:
            return i, found, None
    return best[1], best[2], best


def _ingest(rows, resolver=None) -> dict:
    """rows: [(row_no, name_or_ticker, qty, price)] -> holdings (curated + resolved) and unresolved."""
    merged, pending, unresolved, matched = {}, [], [], []

    def add(t, q, p, extra=None):
        if t in merged:
            m = merged[t]
            tq = m["quantity"] + q
            m["avg_buy_price"] = (m["quantity"] * m["avg_buy_price"] + q * p) / tq
            m["quantity"] = tq
        else:
            merged[t] = {"ticker": t, "quantity": q, "avg_buy_price": p, **(extra or {})}

    for _, name, q, p in rows:
        t = _resolve(name)
        if t:
            add(t, q, p)
        else:
            pending.append((name, q, p))
    found = {}
    if pending and resolver:
        try:
            found = resolver(list(dict.fromkeys(nm for nm, _, _ in pending))[:MAX_LOOKUPS]) or {}
        except Exception:
            found = {}
    for nm, q, p in pending:
        f = found.get(nm)
        if f and f.get("curated"):
            add(f["ticker"], q, p)
        elif f:
            add(f["ticker"], q, p, {"name": f["name"], "sector": f["sector"], "symbol": f["ticker"]})
            matched.append(f"'{nm}' matched to {f['name']} ({f['ticker']}, {f['sector']})")
        else:
            unresolved.append({"name": nm, "quantity": q, "avg_buy_price": p})
    warnings = []
    if matched:
        warnings.append("Matched using Yahoo Finance search, please double-check: " + "; ".join(matched) + ".")
    if unresolved:
        warnings.append(f"{len(unresolved)} holding(s) couldn't be matched to a listed stock: "
                        + ", ".join(u["name"] for u in unresolved) + ". Fix them below or remove them.")
    if not merged and not unresolved:
        return _fail("No valid rows found after validation.", kind="no_rows")
    n = len(merged)
    return {"ok": True, "holdings": list(merged.values()), "unresolved": unresolved, "warnings": warnings,
            "message": f"Found {n} holding{'s' if n != 1 else ''} ready to review."
                       + (f" {len(unresolved)} need attention." if unresolved else "")}


def parse_csv(text: str, resolver=None) -> dict:
    invalid = "File doesn't appear to be a valid CSV. Please check the format."
    text = (text or "").lstrip("\ufeff")
    if not text.strip() or "\x00" in text:
        return _fail(invalid)
    delim = ","
    try:
        delim = csv.Sniffer().sniff(text[:3000], delimiters=",;\t|").delimiter
    except csv.Error:
        pass
    try:
        rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)]
    except csv.Error:
        return _fail(invalid)
    if not rows or any(len(c) > 300 for r in rows[:8] for c in r):
        return _fail(invalid)
    hi, cols, best = _find_table(rows)
    if best is not None:   # no row had all three columns
        need = {"ticker": "stock name or ticker", "quantity": "quantity", "avg_buy_price": "average buy price"}
        missing = [need[k] for k in need if k not in (cols or {})]
        seen = [c.strip() for c in (rows[hi] if hi is not None else rows[0]) if c.strip()]
        return _fail("Couldn't find a holdings table. Still missing column(s): " + ", ".join(missing) +
                     ". The closest header row I found had: " + (", ".join(seen) or "(nothing)") +
                     ". Expected columns like: ticker (or Stock Name), quantity, avg_buy_price (or Average buy price).",
                     kind="no_table")
    data, bad = [], []
    for n, r in enumerate(rows[hi + 1:], start=hi + 2):
        cell = lambda k: r[cols[k]].strip() if cols[k] < len(r) else ""
        name = cell("ticker")
        if not name or not cell("quantity") or name.lower() in ("total", "grand total", "totals"):
            continue                                    # blank / summary / footer line
        try:
            q, p = _n(cell("quantity")), _n(cell("avg_buy_price"))
            if q <= 0 or p < 0:
                raise ValueError
        except ValueError:
            bad.append(n)
            continue
        data.append((n, name, q, p))
    out = _ingest(data, resolver)
    if out["ok"] and bad:
        out["warnings"].append("Rows with an invalid quantity/price were skipped (row numbers): " + ", ".join(map(str, bad)) + ".")
    return out


# ---------- free text / PDF text ----------
_ISIN = re.compile(r"\bIN[EF][A-Z0-9]{9}\b")
_NUMRE = r"\d[\d,]*(?:\.\d+)?"
_NUM = re.compile(rf"(?<![\w.]){_NUMRE}(?![\w])")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}")
_NL = re.compile(rf"({_NUMRE})\s*(?:shares?|qty|units)?\s*(?:of)\s+(.+?)\s+(?:at|@|for)\s*(?:rs\.?|\u20b9|inr)?\s*({_NUMRE})", re.I)
_LEAD = re.compile(r"^([A-Za-z][A-Za-z0-9&.\-' ]*?)[\s,|:x@\-]*(?=\d)")
_SKIP = {"value", "total", "summary", "statement", "client", "code", "holdings", "invested", "closing", "unrealised",
         "realised", "pnl", "balance", "page", "date", "name", "stock", "symbol", "isin", "quantity", "qty",
         "average", "avg", "price", "ltp"}


def parse_lines(text: str):
    """Best-effort reader for pasted text and PDF text: 'TCS 10 3500', 'INFOSYS LTD INE009A01021 10 1500 ...',
    '10 shares of Infosys at 1500'. Column order (qty vs avg price) follows a header line if present."""
    rows, qty_first, prev = [], True, ""
    for n, l in enumerate(text.splitlines(), 1):
        l = l.strip()
        if not l:
            continue
        low = l.lower()
        if ("avg" in low or "average" in low) and ("qty" in low or "quantity" in low):
            pq = min(low.find(k) for k in ("qty", "quantity") if k in low)
            pa = min(low.find(k) for k in ("avg", "average") if k in low)
            qty_first, prev = pq < pa, ""
            continue
        nl = _NL.search(l)
        if nl:
            rows.append((n, nl.group(2).strip(" ,."), _n(nl.group(1)), _n(nl.group(3))))
            continue
        name, nums = None, []
        m = _ISIN.search(l)
        if m:
            name, nums = (l[:m.start()].strip(" ,-|") or prev), _NUM.findall(l[m.end():])
        elif not _DATE.search(l):
            lead = _LEAD.match(l)
            if lead:
                name, nums = lead.group(1).strip(" ,-|."), _NUM.findall(l[lead.end():])
                if {w.lower() for w in re.findall(r"[A-Za-z]+", name)} & _SKIP:
                    name = None
        if name and len(nums) >= 2:
            a, b = _n(nums[0]), _n(nums[1])
            q, p = (a, b) if qty_first else (b, a)
            if q > 0 and p >= 0 and re.search(r"[A-Za-z]{2}", name):
                rows.append((n, name, q, p))
        elif not nums:
            prev = l   # possibly the first half of a wrapped company name
    return rows


def parse_any(text: str, resolver=None) -> dict:
    """Try a real table first (CSV / broker export); fall back to line-by-line text."""
    r = parse_csv(text, resolver)
    if r["ok"] or r.get("kind") != "no_table":
        return r
    rows = parse_lines(text or "")
    if not rows:
        return r      # keep the specific table error
    out = _ingest(rows, resolver)
    if out["ok"]:
        out["warnings"].insert(0, "No table headers found, so I read this as plain text. Please check every quantity and price below.")
    return out


def pdf_to_text(raw: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(raw))
    if reader.is_encrypted:
        try:
            ok = reader.decrypt("")
        except Exception:
            ok = 0
        if not ok:
            raise ValueError("This PDF is password-protected (broker PDFs are often locked with your PAN or date of "
                             "birth). Remove the password, or export the statement as CSV instead.")
    text = "\n".join((pg.extract_text() or "") for pg in reader.pages)
    if not text.strip():
        raise ValueError("This PDF has no readable text (it may be a scanned image). Try the CSV export, or add holdings manually.")
    return text


def band(hhi: float) -> dict:
    if hhi < 1500:
        return {"label": "Well Spread", "level": "good", "text": "Your money is spread across sectors reasonably evenly."}
    if hhi < 2500:
        return {"label": "Moderately Concentrated", "level": "amber", "text": "A few sectors hold a large share of your money."}
    return {"label": "Highly Concentrated", "level": "red", "text": "Most of your money sits in very few sectors."}


def _hhi(weights) -> float:
    return sum((w * 100) ** 2 for w in weights)


def analyze(holdings: list, quotes: dict) -> dict:
    rows = []
    for h in holdings:
        u, q = info(h["ticker"]), quotes.get(h["ticker"])
        price = q["price"] if q else h["avg_buy_price"]
        val, cost = h["quantity"] * price, h["quantity"] * h["avg_buy_price"]
        rows.append({**h, "name": u["name"], "sector": u["sector"], "price": price, "value": val,
                     "cost": cost, "pnl": val - cost, "pnl_pct": (val / cost - 1) * 100 if cost else None,
                     "day_change_pct": q["change_pct"] if q else None,
                     "as_of": q["as_of"] if q else None, "stale": (q or {}).get("stale", True),
                     "price_found": bool(q)})
    total = sum(r["value"] for r in rows)
    for r in rows:
        r["weight"] = r["value"] / total if total else 0.0
    sw = defaultdict(float)
    for r in rows:
        sw[r["sector"]] += r["weight"]
    sw = dict(sorted(sw.items(), key=lambda kv: -kv[1]))
    hhi = _hhi(sw.values())
    cost_total = sum(r["cost"] for r in rows)
    times = [r["as_of"] for r in rows if r["as_of"]]
    top = next(iter(sw), None)
    return {
        "holdings": rows, "total_value": total, "total_cost": cost_total,
        "pnl": total - cost_total, "pnl_pct": (total / cost_total - 1) * 100 if cost_total else None,
        "sector_weights": sw, "hhi": round(hhi), "holding_hhi": round(_hhi(r["weight"] for r in rows)),
        "band": band(hhi), "hhi_explain": HHI_EXPLAIN, "num_holdings": len(rows), "num_sectors": len(sw),
        "top_sector": top, "top_sector_weight": sw.get(top, 0.0) if top else 0.0,
        "prices_as_of": min(times) if times else None,
    }


def simulate_addition(port: dict, ticker: str, amount: float) -> dict:
    """Descriptive what-if: how would concentration change if `amount` INR more sat in this stock."""
    sector = UNIVERSE[ticker]["sector"]
    tot = port["total_value"]
    vals = {s: w * tot for s, w in port["sector_weights"].items()}
    vals[sector] = vals.get(sector, 0.0) + amount
    new_tot = tot + amount
    after = {s: v / new_tot for s, v in vals.items()}
    before_w = port["sector_weights"].get(sector, 0.0)
    hhi_after = round(_hhi(after.values()))
    return {"sector": sector, "amount": amount, "sector_before": before_w, "sector_after": after[sector],
            "hhi_before": port["hhi"], "hhi_after": hhi_after, "band_after": band(hhi_after)["label"],
            "text": (f"If about Rs {amount:,.0f} more were held in this stock, your {sector} share would move from "
                     f"{before_w*100:.1f}% to {after[sector]*100:.1f}% and your concentration band would read "
                     f"'{band(hhi_after)['label']}' (currently '{port['band']['label']}'). This is an illustration, not a suggestion.")}
