"""Shock-origin backtest. Generates bidup101_methodology.md with a coverage table that matches the code.

    python -m bidup101_app.bidup101_backtest

For every node (sector or crude oil) we find non-overlapping historical windows where its 5-day move was <= -2 sigma
(the 'shock origin'), then check (a) whether the alert rule would have flagged any correlated neighbour, and
(b) whether flagged neighbours actually fell over the next 5 days. Sample sizes are reported prominently.
"""
import datetime as dt
import numpy as np

from . import bidup101_config as cfg
from . import bidup101_market as market
from . import bidup101_risk as risk
from . import bidup101_gat as gat


def run():
    hist = market.download_history("6y")
    Rdf = risk.build_returns(hist)
    R, nodes = Rdf.values, list(Rdf.columns)
    model = gat.get_model()
    stats = {n: {"windows": 0, "alerted": 0, "fell": 0} for n in nodes}
    last = {n: -99 for n in nodes}
    for t in range(risk.WINDOW - 1, len(R) - 5):
        X, corr = risk.features_at(R, t)
        A = risk.adjacency(corr)
        stress = gat.stress_vector(X)
        for j, n in enumerate(nodes):
            if X[j, 0] > -2 or t - last[n] < 10:
                continue
            last[n] = t
            stats[n]["windows"] += 1
            scores, _, _ = model.score(X, A, corr)
            nbrs = [i for i in range(len(nodes)) if i != j and A[i, j] and scores[i] >= model.threshold]
            if nbrs:
                stats[n]["alerted"] += 1
                fwd = np.mean([np.prod(1 + R[t + 1: t + 6, i]) - 1 for i in nbrs])
                stats[n]["fell"] += int(fwd < 0)
    lines = ["# BidUp101 - Methodology and Backtest", "",
             f"_Generated {dt.date.today()} from data {hist.index[0].date()} to {hist.index[-1].date()}._", "",
             "## Model", f"- Method in use: **{'trained Graph Attention Network' if model.trained else 'UNTRAINED correlation-attention heuristic (parameters are illustrative, not fitted)'}**.",
             "- Nodes: equal-weighted sector return series built from the supported NSE universe, plus Crude Oil (CL=F).",
             f"- Edges: trailing {risk.WINDOW}-day correlation >= {risk.CORR_EDGE}. Features: 5d/20d z-scores, volatility ratio, vol trend, mean |corr|.",
             "- Alerts are descriptive only. They are not investment advice.", ""]
    if model.metrics:
        m = model.metrics
        lines += ["## Held-out test metrics (chronological split, 5-day purge)",
                  f"- Test days: {m.get('n_test_days')}, adverse events: {m.get('n_test_positive_events')} (base rate {m.get('test_base_rate', 0):.3f})",
                  f"- AUC GAT: {m.get('test_auc_gat')}; AUC untrained heuristic baseline: {m.get('test_auc_heuristic_baseline')}",
                  f"- Precision/recall at chosen threshold: {m.get('test_precision_at_threshold', 0):.2f} / {m.get('test_recall_at_threshold', 0):.2f}", ""]
    lines += ["## Coverage table (alert rule vs backtest)", "",
              "| Sector | Alert Rule Exists | Backtested as Shock Origin | Shock windows (n) | Neighbour alert raised (n) | Neighbours fell next 5d (of alerted) |",
              "|---|---|---|---|---|---|"]
    for n in nodes:
        s = stats[n]
        lines.append(f"| {n} | ✅ | {'✅' if s['windows'] else '❌ (no qualifying windows in sample)'} | {s['windows']} | {s['alerted']} | {s['fell']} of {s['alerted']} |")
    lines += ["", "## Honest limitations",
              "- Sample sizes per sector are small (see n above). Do NOT read hit counts as accuracy percentages.",
              "- Sector series are equal-weighted proxies of a 38-stock universe, not official NSE indices.",
              "- Alert thresholds (stress >= 0.5 as driver, exposure >= 5%) are design choices, not statistically optimised.",
              "- Past co-movement does not imply future propagation. yfinance data is delayed and unadjusted for survivorship."]
    cfg.METHODOLOGY_FILE.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    run()
