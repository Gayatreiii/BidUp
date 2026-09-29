"""Natural-language stock screener: LLM extracts filters (rule-based fallback), then deterministic filtering."""
import json
import re
import pandas as pd

from . import bidup101_llm as llm
from . import bidup101_market as market
from . import bidup101_indicators as ind
from .bidup101_universe import UNIVERSE, SECTORS

_SYN = {"it": "IT", "tech": "IT", "technology": "IT", "software": "IT", "bank": "Banking", "banks": "Banking",
        "banking": "Banking", "financial": "Banking", "energy": "Energy", "oil": "Energy", "gas": "Energy",
        "metal": "Metals", "metals": "Metals", "steel": "Metals", "auto": "Auto", "automobile": "Auto",
        "automobiles": "Auto", "fmcg": "FMCG", "consumer": "FMCG", "pharma": "Pharma", "pharmaceutical": "Pharma",
        "healthcare": "Pharma", "telecom": "Telecom", "infra": "Infra", "infrastructure": "Infra", "cement": "Infra"}
_EXCL = ("exclude", "excluding", "avoid", "without", "except", "no", "not", "ignore", "skip")
_cache = {"ver": None, "df": None}


def dataset() -> pd.DataFrame:
    hist = market.get_history()
    ver = market.history_version()
    if _cache["ver"] == ver and _cache["df"] is not None:
        return _cache["df"]
    rows = []
    for t, u in UNIVERSE.items():
        if t not in hist:
            continue
        s = hist[t].dropna()
        if len(s) < 40:
            continue
        rets = s.pct_change().dropna()
        rows.append({"ticker": t, "name": u["name"], "sector": u["sector"], "price": float(s.iloc[-1]),
                     "rsi": ind.rsi_last(s), "return_1m_pct": float((s.iloc[-1] / s.iloc[-21] - 1) * 100),
                     "volatility_pct": float(rets.std() * (252 ** 0.5) * 100)})
    df = pd.DataFrame(rows)
    q1, q2 = df["volatility_pct"].quantile([1 / 3, 2 / 3])
    df["risk"] = df["volatility_pct"].apply(lambda v: "Low" if v <= q1 else "Medium" if v <= q2 else "High")
    _cache.update(ver=ver, df=df)
    return df


def _rules(q: str) -> dict:
    ql, f = q.lower(), {"include_sectors": [], "exclude_sectors": [], "rsi_min": None, "rsi_max": None, "risk": []}
    for m in re.finditer(r"\b(" + "|".join(sorted(_SYN, key=len, reverse=True)) + r")\b", ql):
        sec, before = _SYN[m.group(1)], ql[max(0, m.start() - 22): m.start()]
        target = f["exclude_sectors"] if any(re.search(rf"\b{w}\b", before) for w in _EXCL) else f["include_sectors"]
        if sec not in target:
            target.append(sec)
    if "oversold" in ql:
        f["rsi_max"] = 30
    if "overbought" in ql:
        f["rsi_min"] = 70
    m = re.search(r"rsi\s*(?:is\s*)?(below|under|<|less than|above|over|>|more than|greater than)\s*(\d+)", ql)
    if m:
        (f.__setitem__("rsi_max", int(m.group(2))) if m.group(1) in ("below", "under", "<", "less than")
         else f.__setitem__("rsi_min", int(m.group(2))))
    for r in ("low", "medium", "high"):
        if re.search(rf"\b{r}[\s-]*risk", ql):
            f["risk"].append(r.capitalize())
    return f


def _llm_filters(q: str):
    prompt = ("Extract stock screener filters from the request. Valid sectors: " + ", ".join(SECTORS) + ". "
              'Reply ONLY JSON: {"include_sectors":[],"exclude_sectors":[],"rsi_min":null,"rsi_max":null,'
              '"risk":[]} where risk items are Low/Medium/High.\nRequest: ' + q)
    out = llm.complete([{"role": "user", "content": prompt}], max_tokens=200, temperature=0)
    d = json.loads(re.search(r"\{.*\}", out, re.S).group(0))
    return {"include_sectors": [s for s in d.get("include_sectors", []) if s in SECTORS],
            "exclude_sectors": [s for s in d.get("exclude_sectors", []) if s in SECTORS],
            "rsi_min": d.get("rsi_min"), "rsi_max": d.get("rsi_max"),
            "risk": [r for r in d.get("risk", []) if r in ("Low", "Medium", "High")]}


def describe(f: dict) -> str:
    parts = []
    if f["include_sectors"]:
        parts.append("sectors: " + ", ".join(f["include_sectors"]))
    if f["exclude_sectors"]:
        parts.append("excluding: " + ", ".join(f["exclude_sectors"]))
    if f["rsi_max"] is not None:
        parts.append(f"RSI below {f['rsi_max']}")
    if f["rsi_min"] is not None:
        parts.append(f"RSI above {f['rsi_min']}")
    if f["risk"]:
        parts.append("risk level: " + "/".join(f["risk"]))
    return "; ".join(parts) or "no filters recognised (showing everything)"


def run(query: str) -> dict:
    method = "rules"
    try:
        f, method = _llm_filters(query), "llm"
    except Exception:
        f = _rules(query)
    df = dataset()
    if f["include_sectors"]:
        df = df[df["sector"].isin(f["include_sectors"])]
    if f["exclude_sectors"]:
        df = df[~df["sector"].isin(f["exclude_sectors"])]
    if f["rsi_max"] is not None:
        df = df[df["rsi"] <= float(f["rsi_max"])]
    if f["rsi_min"] is not None:
        df = df[df["rsi"] >= float(f["rsi_min"])]
    if f["risk"]:
        df = df[df["risk"].isin(f["risk"])]
    df = df.sort_values("rsi")
    return {"filters": f, "interpreted_as": describe(f), "parser": method, "count": int(len(df)),
            "results": [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in r.items()}
                        for r in df.to_dict("records")],
            "note": "Results list stocks that match your filters. They are not recommendations."}
