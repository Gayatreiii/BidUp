"""Cross-sector risk propagation: sector graph -> GAT scores -> plain-language descriptive alerts."""
import numpy as np
import pandas as pd

from .bidup101_universe import UNIVERSE, CRUDE_NODE, CRUDE_COLUMN
from . import bidup101_gat as gat

WINDOW = 120
CORR_EDGE = 0.30
DRIVER_STRESS = 0.5
MIN_EXPOSURE = 0.05


def build_returns(hist: pd.DataFrame) -> pd.DataFrame:
    """Equal-weighted daily sector returns (+ crude oil) from constituent closes."""
    rets = hist.pct_change().iloc[1:]
    cols = {}
    for sector in sorted({v["sector"] for v in UNIVERSE.values()}):
        members = [t for t, v in UNIVERSE.items() if v["sector"] == sector and t in rets.columns]
        if members:
            cols[sector] = rets[members].mean(axis=1)
    if CRUDE_COLUMN in rets.columns:
        cols[CRUDE_NODE] = rets[CRUDE_COLUMN]
    return pd.DataFrame(cols).fillna(0.0)


def features_at(R: np.ndarray, t: int):
    """Node features + correlation for the trailing WINDOW ending at row t (inclusive)."""
    W = R[t - WINDOW + 1: t + 1]
    sd = W.std(0) + 1e-8
    z5 = W[-5:].sum(0) / (sd * np.sqrt(5))
    z20 = W[-20:].sum(0) / (sd * np.sqrt(20))
    vr = np.sqrt((W[-5:] ** 2).mean(0)) / (np.sqrt((W[-60:] ** 2).mean(0)) + 1e-8)
    vlr = np.log((W[-20:].std(0) + 1e-8) / sd)
    corr = np.nan_to_num(np.corrcoef(W.T))
    n = W.shape[1]
    mc = (np.abs(corr).sum(1) - 1) / max(n - 1, 1)
    return np.clip(np.stack([z5, z20, vr - 1, vlr, mc], 1), -5, 5), corr


def adjacency(corr: np.ndarray) -> np.ndarray:
    A = corr >= CORR_EDGE
    np.fill_diagonal(A, True)
    return A


def _reason(x) -> str:
    return "a sharp recent decline" if x[0] <= -1 else "unusually high volatility"


def assess(hist: pd.DataFrame, sector_weights: dict) -> dict:
    R = build_returns(hist)
    if len(R) < WINDOW + 1 or R.shape[1] < 3:
        raise ValueError("Not enough history for the risk model.")
    X, corr = features_at(R.values, len(R) - 1)
    A = adjacency(corr)
    model = gat.get_model()
    scores, att, method = model.score(X, A, corr)
    stress = gat.stress_vector(X)
    nodes = list(R.columns)
    thr = model.threshold

    alerts = []
    for i, name in enumerate(nodes):
        w = sector_weights.get(name, 0.0)
        if w < MIN_EXPOSURE or scores[i] < thr:
            continue
        drivers = sorted(((att[i, j] * stress[j], j) for j in range(len(nodes))
                          if j != i and stress[j] >= DRIVER_STRESS and A[i, j]), reverse=True)
        level = "Elevated" if scores[i] >= 0.7 else "Watch"
        if drivers:
            j = drivers[0][1]
            text = (f"Your {name} holdings ({w*100:.0f}% of your portfolio) show elevated correlation with "
                    f"{nodes[j]}, which is currently showing {_reason(X[j])}.")
            origin = nodes[j]
        else:
            text = (f"The {name} sector is currently showing {_reason(X[i])}; "
                    f"your holdings there are {w*100:.0f}% of your portfolio.")
            origin = name
        alerts.append({"key": f"{name}|{origin}|{level}", "sector": name, "origin": origin, "level": level,
                       "score": round(float(scores[i]), 2), "text": text})
    alerts.sort(key=lambda a: -a["score"])

    edges = []
    for i in range(len(nodes)):
        for j in range(len(nodes)):
            if i != j and A[i, j]:
                edges.append({"target": nodes[i], "source": nodes[j], "attention": round(float(att[i, j]), 3),
                              "correlation": round(float(corr[i, j]), 2)})
    edges.sort(key=lambda e: -e["attention"])
    return {
        "method": method, "trained": model.trained, "threshold": round(thr, 2), "metrics": model.metrics,
        "as_of": str(R.index[-1])[:10],
        "nodes": [{"node": n, "stress": round(float(stress[k]), 2), "score": round(float(scores[k]), 2),
                   "z5": round(float(X[k, 0]), 2), "vol_ratio": round(float(X[k, 2] + 1), 2)}
                  for k, n in enumerate(nodes)],
        "edges": edges[:25], "alerts": alerts,
        "uncovered_weight": round(max(0.0, 1 - sum(sector_weights.get(n, 0.0) for n in nodes)), 4),
        "disclosure": ("Scores come from a trained Graph Attention Network." if model.trained else
                       "No trained model file found: scores use an untrained correlation-attention heuristic with "
                       "illustrative parameters (not fitted). See Methodology."),
    }
