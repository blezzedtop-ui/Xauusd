# SignalX Execution Gate V3 — 2026-09-17

Pipeline:
`Signal -> Geometry Check -> Target Check -> Risk Check -> AutoTrade`

Applied to each supported module signal on XAU/USD for 5min, 15min, 30min, 1h, 4h and 1day.

## Rules
- Every BUY/SELL module signal is persisted to Signal History with its source/module.
- M1/1min/1m is analysis/history-only and is never sent to MT5 AutoTrade.
- Geometry is checked against the original signal values before any normalization.
  - BUY: `SL < Entry < TP`
  - SELL: `TP < Entry < SL`
- Wrong-side existing SL is never silently repaired. It becomes `CANCELLED / INVALID_LEVEL_GEOMETRY` and cannot enter the MT5 queue.
- If TP is missing or on the wrong side, Target Check searches the next valid structural resistance/support (including pivot R2/R3 or S2/S3 and other structural levels).
- If no valid target exists: `WAIT / TARGET_REACHED`; no AutoTrade.
- Risk Check uses the exact levels that would be sent to MT5.
- Execution RR must be at least 1.50 and structural risk must remain within the configured adaptive risk limit.
- Failed Risk Check: `CANCELLED / RISK_CHECK_FAILED` or `CANCELLED / RR_BELOW_1_50`; no AutoTrade.
- Only `READY / ALL_GATES_PASSED` signals are eligible for the MT5 queue.
- Duplicate queue protection remains keyed by market/source/timeframe/candle/direction.
- Book + OpenAI remains excluded from the MT5 queue.
