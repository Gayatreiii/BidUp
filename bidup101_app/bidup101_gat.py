"""Graph Attention Network inference in pure numpy (weights trained offline by bidup101_train_gat.py).

If no trained weights exist, an UNTRAINED correlation-attention propagation heuristic is used and
labelled as such everywhere in the API/UI. Never present the heuristic as a fitted model.
"""
import json
from functools import lru_cache
import numpy as np

from . import bidup101_config as cfg

DEFAULT_THRESHOLD = 0.45


def _lrelu(x, s=0.2):
    return np.where(x > 0, x, s * x)


def _elu(x):
    return np.where(x > 0, x, np.exp(np.minimum(x, 0)) - 1)


def masked_softmax(e, mask):
    e = np.where(mask, e, -1e9)
    e = e - e.max(-1, keepdims=True)
    p = np.exp(e) * mask
    return p / (p.sum(-1, keepdims=True) + 1e-12)


def stress_vector(X: np.ndarray) -> np.ndarray:
    """Adverse-move intensity per node from features [z5, z20, vol_ratio-1, ...]."""
    return np.clip(np.maximum(0, -X[:, 0]) / 2 + np.maximum(0, X[:, 2]) / 1.5, 0, 1.5)


class Bidup101GatModel:
    def __init__(self, weights=None, metrics=None):
        self.w = weights
        self.metrics = metrics or {}

    @property
    def trained(self) -> bool:
        return self.w is not None

    @property
    def threshold(self) -> float:
        return float(self.metrics.get("threshold", DEFAULT_THRESHOLD)) if self.trained else DEFAULT_THRESHOLD

    def score(self, X: np.ndarray, A: np.ndarray, corr: np.ndarray):
        """Return (scores per node in 0..1, attention matrix (N,N), method name)."""
        if not self.trained:
            return self._heuristic(X, A, corr)
        W, a_src, a_dst, Wo, bo = (self.w[k] for k in ("W", "a_src", "a_dst", "Wo", "bo"))
        h = np.einsum("nf,kfh->knh", X, W)
        es, ed = (h * a_src[:, None, :]).sum(-1), (h * a_dst[:, None, :]).sum(-1)
        att = masked_softmax(_lrelu(es[:, :, None] + ed[:, None, :]), A[None])
        o = _elu(np.einsum("knm,kmh->knh", att, h)).transpose(1, 0, 2).reshape(X.shape[0], -1)
        logits = (o @ Wo).squeeze(-1) + float(np.ravel(bo)[0])
        return 1 / (1 + np.exp(-logits)), att.mean(0), "gat_trained"

    def _heuristic(self, X, A, corr):
        stress = stress_vector(X)
        mask = A & ~np.eye(len(A), dtype=bool)
        att = masked_softmax(4.0 * corr, mask)                      # attention ~ softmax of correlation
        prop = att @ stress                                          # neighbour stress, attention-weighted
        scores = np.clip(0.7 * stress + 0.7 * prop, 0, 1)            # illustrative weights, NOT fitted
        return scores, att, "correlation_attention_heuristic"


@lru_cache(maxsize=1)
def get_model() -> Bidup101GatModel:
    if cfg.GAT_WEIGHTS_FILE.exists():
        try:
            z = np.load(cfg.GAT_WEIGHTS_FILE)
            metrics = json.loads(cfg.GAT_METRICS_FILE.read_text()) if cfg.GAT_METRICS_FILE.exists() else {}
            return Bidup101GatModel({k: z[k] for k in ("W", "a_src", "a_dst", "Wo", "bo")}, metrics)
        except Exception:
            pass
    return Bidup101GatModel()
