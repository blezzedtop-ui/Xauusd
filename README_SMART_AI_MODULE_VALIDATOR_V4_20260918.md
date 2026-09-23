# SignalX Smart AI Module Validator V4 — 2026-09-18

## What changed

Every AutoTrade-capable signal module now receives its own AI validation on the same live candle before the execution gate.

Modules covered:
- Signal Lab
- Signals
- AlgoTrade
- Technical Analysis
- Classic Trade
- SNR
- Auto Trend Line
- ICT Signals
- AI Smart Analysis
- Book + OpenAI already had its own AI second-opinion layer and remains History/analysis only.

## New pipeline

Signal -> Per-module AI Validation -> Smart Market/Structure Validation -> Geometry -> TP1 Target Check -> Risk Check -> MT5 AutoTrade

If AI/market quality fails, the original module signal is still preserved in Signal History, but it is not sent to AutoTrade.

## AI behavior

The existing multi-provider AI router is reused. It can fail over across configured providers and falls back to deterministic validation when providers are unavailable. The system does not claim deterministic fallback is live AI.

Live AI AutoTrade validation requires:
- AI direction agrees with the module direction
- AI confidence >= 65
- AI agreement >= 55
- deterministic module quality >= 60
- no strong market-regime conflict
- no strong opposite structure conflict

Fallback/rule-based mode does not pretend to be AI; it keeps the deterministic candidate alive so the independent execution/risk gate remains responsible for geometry, TP1 and maximum SL risk.

## Trading constraints preserved

- M1 is never sent to AutoTrade.
- TP2 is optional and never required for AutoTrade.
- RR >= 1.50 is NOT an AutoTrade gate.
- Risk protection remains independent of RR.
- Invalid geometry is blocked.
- Wrong-side TP is repaired using structural target search where possible.
- No valid TP1 means no AutoTrade.
- Book + OpenAI remains excluded from AutoTrade.

## Important distinction

The previous implementation marked several deterministic components as `ai_assisted`, but in the AutoTrade candidate loop only the shared Signal Lab validation was guaranteed before this change. V4 makes the AI validation explicit per module instead of only labeling components as AI-assisted.
