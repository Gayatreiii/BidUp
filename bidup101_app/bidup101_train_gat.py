"""Offline training of the sector-graph GAT. Run locally (needs torch + internet):

    pip install -r bidup101_requirements_train.txt
    python -m bidup101_app.bidup101_train_gat

Task: for each sector node (and crude oil) predict whether its NEXT-5-DAY return will fall below -1 trailing sigma
(5-day scale). Chronological train/val/test split with a 5-day purge gap. Saves weights (npz) + metrics (json),
including baselines, so the thesis can report GAT vs heuristic vs base rate honestly.
"""
import json
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from . import bidup101_config as cfg
from . import bidup101_market as market
from . import bidup101_risk as risk
from . import bidup101_gat as gat

SEED, K, H, EPOCHS, LR = 7, 4, 16, 400, 5e-3


class Bidup101DenseGat(nn.Module):
    def __init__(self, f_in, hidden=H, heads=K):
        super().__init__()
        self.W = nn.Parameter(torch.randn(heads, f_in, hidden) * 0.3)
        self.a_src = nn.Parameter(torch.randn(heads, hidden) * 0.3)
        self.a_dst = nn.Parameter(torch.randn(heads, hidden) * 0.3)
        self.out = nn.Linear(heads * hidden, 1)

    def forward(self, X, A):                      # X (B,N,F), A (B,N,N) bool
        h = torch.einsum("bnf,kfh->bknh", X, self.W)
        es, ed = (h * self.a_src[None, :, None, :]).sum(-1), (h * self.a_dst[None, :, None, :]).sum(-1)
        e = F.leaky_relu(es[..., :, None] + ed[..., None, :], 0.2)
        e = e.masked_fill(~A[:, None], -1e9)
        att = torch.softmax(e, -1)
        o = F.elu(torch.einsum("bknm,bkmh->bknh", att, h))
        B, _, N, _ = o.shape
        return self.out(o.permute(0, 2, 1, 3).reshape(B, N, -1)).squeeze(-1)


def build_dataset(R: np.ndarray):
    Xs, As, Ys, Cs = [], [], [], []
    for t in range(risk.WINDOW - 1, R.shape[0] - 5):
        X, corr = risk.features_at(R, t)
        sd = R[t - risk.WINDOW + 1: t + 1].std(0) + 1e-8
        fwd = np.prod(1 + R[t + 1: t + 6], axis=0) - 1
        Xs.append(X); Cs.append(corr); As.append(risk.adjacency(corr)); Ys.append((fwd < -1.0 * sd * np.sqrt(5)).astype(np.float32))
    return np.stack(Xs).astype(np.float32), np.stack(As), np.stack(Ys), np.stack(Cs)


def auc(y, s):
    y, s = np.asarray(y).ravel(), np.asarray(s).ravel()
    pos, neg = s[y == 1], s[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return None
    ranks = np.argsort(np.argsort(np.concatenate([pos, neg]))) + 1
    return float((ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def best_threshold(y, p):
    best, thr = -1, 0.5
    for t in np.linspace(0.1, 0.9, 33):
        pred = p >= t
        tp = (pred & (y == 1)).sum(); prec = tp / max(pred.sum(), 1); rec = tp / max((y == 1).sum(), 1)
        f1 = 2 * prec * rec / max(prec + rec, 1e-9)
        if f1 > best:
            best, thr = f1, float(t)
    return thr


def main():
    torch.manual_seed(SEED); np.random.seed(SEED)
    hist = market.download_history("6y")
    R = risk.build_returns(hist).values
    X, A, Y, C = build_dataset(R)
    n = len(X); i1, i2 = int(n * 0.70), int(n * 0.85)
    sl = {"train": slice(0, i1), "val": slice(i1 + 5, i2), "test": slice(i2 + 5, n)}   # 5-day purge gaps
    Xt, At, Yt = torch.tensor(X), torch.tensor(A), torch.tensor(Y)
    model = Bidup101DenseGat(X.shape[-1])
    opt = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=1e-3)
    pw = torch.tensor((1 - Y[sl["train"]].mean()) / max(Y[sl["train"]].mean(), 1e-3))
    best, best_state, bad = 1e9, None, 0
    for ep in range(EPOCHS):
        model.train(); opt.zero_grad()
        loss = F.binary_cross_entropy_with_logits(model(Xt[sl["train"]], At[sl["train"]]), Yt[sl["train"]], pos_weight=pw)
        loss.backward(); opt.step()
        model.eval()
        with torch.no_grad():
            vl = F.binary_cross_entropy_with_logits(model(Xt[sl["val"]], At[sl["val"]]), Yt[sl["val"]], pos_weight=pw).item()
        if vl < best - 1e-4:
            best, bad = vl, 0
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
            if bad >= 40:
                break
    model.load_state_dict(best_state); model.eval()
    with torch.no_grad():
        prob = {k: torch.sigmoid(model(Xt[s], At[s])).numpy() for k, s in sl.items()}
    thr = best_threshold(Y[sl["val"]], prob["val"])
    heur = gat.Bidup101GatModel(None)
    hs = np.stack([heur.score(X[i], A[i], C[i])[0] for i in range(sl['test'].start, n)])   # untrained baseline
    yt, pt = Y[sl["test"]], prob["test"]
    pred = pt >= thr
    tp = int((pred & (yt == 1)).sum())
    metrics = {
        "threshold": thr, "epochs_run": ep + 1, "heads": K, "hidden": H, "features": int(X.shape[-1]),
        "n_days": int(n), "n_test_days": int(len(yt)), "n_test_positive_events": int((yt == 1).sum()),
        "test_base_rate": float(yt.mean()), "test_auc_gat": auc(yt, pt), "test_auc_heuristic_baseline": auc(yt, hs),
        "test_precision_at_threshold": float(tp / max(pred.sum(), 1)), "test_recall_at_threshold": float(tp / max((yt == 1).sum(), 1)),
        "target": "next-5-day return < -1 trailing sigma (5d scale)", "split": "70/15/15 chronological with 5-day purge",
        "trained_on": f"{hist.index[0].date()} to {hist.index[-1].date()}",
    }
    cfg.MODEL_DIR.mkdir(exist_ok=True)
    sd = {k: v.detach().numpy() for k, v in model.state_dict().items()}
    np.savez(cfg.GAT_WEIGHTS_FILE, W=sd["W"], a_src=sd["a_src"], a_dst=sd["a_dst"],
             Wo=sd["out.weight"].T.copy(), bo=sd["out.bias"])
    cfg.GAT_METRICS_FILE.write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
