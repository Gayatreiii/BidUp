# BidUp101 - Methodology and Backtest

**Status: the backtest has NOT been run yet.** Run `python -m bidup101_app.bidup101_backtest` (after optionally training
the GAT with `python -m bidup101_app.bidup101_train_gat`). It overwrites this file with real numbers.

## Model
- Until trained weights exist in `bidup101_models/`, the app uses an **untrained correlation-attention heuristic**; its weights
  (0.7 / 0.7, softmax temperature 4) are **illustrative placeholders, not fitted**. The UI labels this everywhere.
- Nodes: equal-weighted sector return series from the supported NSE universe, plus Crude Oil (CL=F).
- Alerts are descriptive only (e.g. "Your Energy holdings show elevated correlation with Crude Oil"). They are not advice.

## Coverage table (alert rule vs backtest)

| Sector | Alert Rule Exists | Backtested as Shock Origin | Shock windows (n) | Neighbour alert raised (n) | Neighbours fell next 5d |
|---|---|---|---|---|---|
| Auto | ✅ | ❌ (backtest not yet run) | - | - | - |
| Banking | ✅ | ❌ (backtest not yet run) | - | - | - |
| Energy | ✅ | ❌ (backtest not yet run) | - | - | - |
| FMCG | ✅ | ❌ (backtest not yet run) | - | - | - |
| IT | ✅ | ❌ (backtest not yet run) | - | - | - |
| Infra | ✅ | ❌ (backtest not yet run) | - | - | - |
| Metals | ✅ | ❌ (backtest not yet run) | - | - | - |
| Pharma | ✅ | ❌ (backtest not yet run) | - | - | - |
| Telecom | ✅ | ❌ (backtest not yet run) | - | - | - |
| Crude Oil | ✅ | ❌ (backtest not yet run) | - | - | - |

Every node can act as a shock origin in the rule, but **none has been validated yet**. This is a disclosed limitation.
