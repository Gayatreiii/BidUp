# BidUp101 — Portfolio Intelligence & Risk Advisory (educational tool, not investment advice)

Single deployable service: **FastAPI** (JSON API + serves the frontend) + plain **HTML/CSS/JS** frontend. No Reflex, no database,
no auth (per your scope). Portfolios live in the user's browser (localStorage) and are sent to the stateless API on each call.
Paper trading and IPO analysis are **not** included.

## Files (every file is prefixed `bidup101`)
| File | Role |
|---|---|
| `bidup101_app/bidup101_main.py` | FastAPI app, all routes, wiring |
| `bidup101_app/bidup101_config.py` | Settings, env var access (secrets never logged) |
| `bidup101_app/bidup101_universe.py` | 38 NSE stocks, sectors, demo portfolio |
| `bidup101_app/bidup101_market.py` | yfinance history + quotes, TTL caches, last-known-price fallback |
| `bidup101_app/bidup101_indicators.py` | RSI/MACD/Bollinger via `ta` + plain-language text |
| `bidup101_app/bidup101_portfolio.py` | CSV validation, valuation, HHI bands, what-if simulation |
| `bidup101_app/bidup101_gat.py` | Graph Attention Network inference (numpy) + labelled heuristic fallback |
| `bidup101_app/bidup101_risk.py` | Sector graph, features, descriptive alerts |
| `bidup101_app/bidup101_news.py` | NewsData.io, real links/timestamps, 25-min cache, sentiment (LLM, lexicon fallback) |
| `bidup101_app/bidup101_llm.py` | Nemotron client, compliance system prompt, output guard |
| `bidup101_app/bidup101_screener.py` | Natural-language screener (LLM filter extraction, rule fallback) |
| `bidup101_app/bidup101_train_gat.py` | **Offline ML training** (PyTorch) → weights + metrics |
| `bidup101_app/bidup101_backtest.py` | Shock-origin backtest → regenerates `bidup101_methodology.md` |
| `bidup101_web/bidup101_index.html`, `_styles.css`, `_client.js` | Frontend |

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r bidup101_requirements.txt
cp bidup101.env.example .env                          # fill NEMOTRON_API_KEY and NEWSDATA_API_KEY; keep .env gitignored
uvicorn bidup101_app.bidup101_main:bidup101_api --reload
# open http://127.0.0.1:8000
```
Without API keys the app still runs: chat shows "AI temporarily unavailable", news shows "not configured", sentiment uses the lexicon.

## Train the ML model (for your thesis)
```bash
pip install -r bidup101_requirements_train.txt
python -m bidup101_app.bidup101_train_gat      # writes bidup101_models/bidup101_gat_weights.npz + metrics json
python -m bidup101_app.bidup101_backtest       # rewrites bidup101_methodology.md with real n's
```
Commit the two files in `bidup101_models/` so the deployed app (numpy only, no torch) serves the trained model. Until then the
app uses an **untrained** correlation-attention heuristic and says so in the UI and methodology. Thesis angle: report GAT vs the
heuristic baseline vs base rate (all in the metrics json), with sample sizes.

## Deploy free (Render)
1. Push to GitHub (ensure `.env` is in `.gitignore`).
2. Render → New → Web Service → connect repo. Runtime **Python 3**, plan **Free**.
3. Build: `pip install -r bidup101_requirements.txt`
4. Start: `uvicorn bidup101_app.bidup101_main:bidup101_api --host 0.0.0.0 --port $PORT`
5. Environment: add `NEMOTRON_API_KEY`, `NEWSDATA_API_KEY`, `PYTHON_VERSION=3.11.9`.
Free instances sleep after idle time (first load is slow). Koyeb and Railway work with the same commands. Hugging Face Docker Spaces
require a file literally named `Dockerfile`, which conflicts with your naming rule, so Render is the simplest fit.

## Colours
Your palette is used throughout. Semantic colours I added because 5 colours aren't enough for status: green `#1a8f55` (Bullish / well
spread), amber `#c77b00` (moderate / watch), red `#e45858` (your tertiary; Bearish / concentrated / elevated), grey for Neutral.

## Honest limitations
- yfinance is ~15 min delayed and rate-limited; the UI says so and keeps last-known prices on failure.
- NewsData.io free tier is limited; news is cached 25 min per ticker and limited to your top 5 holdings.
- Notifications are simulated by a 60-second timer while the page is open.
- Broker sync is a "Coming Soon" card only. Verify NSE tickers in `bidup101_universe.py` (symbols occasionally change).
- Verify the Nemotron model id against NVIDIA docs; override with `BIDUP101_LLM_MODEL`.
