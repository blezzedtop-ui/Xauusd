# SignalX Execution Gate — TP1 Risk Protection (2026-09-17)

Pipeline:
`Signal -> Geometry Check -> Target Check -> Risk Check -> AutoTrade`

## AutoTrade rules
- Every BUY/SELL module signal is persisted to Signal History with its source/module.
- M1/1min/1m is analysis/history-only and is never sent to MT5 AutoTrade.
- Geometry is checked before normalization.
  - BUY: `SL < Entry < TP1`
  - SELL: `TP1 < Entry < SL`
- If the supplied TP is on the wrong side, Target Check searches the next valid structural target.
- If no valid target exists: `WAIT / TARGET_REACHED`; no AutoTrade.
- **TP2 is optional and is NOT an AutoTrade requirement.**
- **RR is informational only and does NOT block AutoTrade.** A setup is not rejected merely because RR is below 1.50.
- Risk protection remains hard: the exact MT5 SL distance must be positive and within the adaptive maximum-risk limit.
- Invalid geometry: `CANCELLED / INVALID_LEVEL_GEOMETRY`; no AutoTrade.
- Failed structural risk check: `CANCELLED / RISK_CHECK_FAILED`; no AutoTrade.
- Only `READY / ALL_GATES_PASSED` signals enter the MT5 queue.
- Duplicate queue protection remains keyed by market/source/timeframe/candle/direction.
- Book + OpenAI remains excluded from the MT5 queue.

## RR meaning
RR is calculated and retained in History/analytics as:
- BUY: `(TP1 - Entry) / (Entry - SL)`
- SELL: `(Entry - TP1) / (SL - Entry)`

It is **not a forecast** and it is **not a gate**. TP1 may be closer than 1.5R and still be eligible if geometry, target and structural-risk checks pass.
