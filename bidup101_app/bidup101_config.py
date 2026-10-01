"""Central configuration for BidUp101. Secrets are read from environment only."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # dotenv optional in production (host injects env vars)
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "bidup101_web"
MODEL_DIR = BASE_DIR / "bidup101_models"
METHODOLOGY_FILE = BASE_DIR / "bidup101_methodology.md"
GAT_WEIGHTS_FILE = MODEL_DIR / "bidup101_gat_weights.npz"
GAT_METRICS_FILE = MODEL_DIR / "bidup101_gat_metrics.json"

LLM_BASE_URL = os.getenv("BIDUP101_LLM_BASE_URL", "https://integrate.api.nvidia.com/v1")
# NVIDIA's catalog changes over time; override with BIDUP101_LLM_MODEL env var if this stops working.
# Current default (as of testing): Nemotron 3 Super, NVIDIA's flagship hosted model on integrate.api.nvidia.com.
LLM_MODEL = os.getenv("BIDUP101_LLM_MODEL", "nvidia/nemotron-3-super-120b-a12b")

HISTORY_TTL_SEC = 1800   # daily history cache
QUOTE_TTL_SEC = 90       # price refresh interval (respects free-tier limits)
NEWS_TTL_SEC = 1500      # per-ticker news cache (25 min)


def env(name: str) -> str:
    """Read a secret/config value. Never log the returned value."""
    return os.getenv(name, "").strip()
