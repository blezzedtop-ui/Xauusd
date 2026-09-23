# SignalX Signal History HTTP 500 FIX V4

Scope: Signal History reliability only. Existing Signal Engine, AlgoTrade, AutoTrade,
MT5 Bridge/Gateway, AI Q&A, and trading strategy logic are not redesigned by this patch.

Fixes:
- `payload.result` may be a legacy string; History now treats it safely instead of calling `.get()` on a string.
- Non-dict JSON payloads are normalized before access.
- History outcome refresh is best-effort and protected by a per-user async lock to prevent concurrent refresh races.
- Malformed/unknown timeframes are skipped during outcome refresh rather than producing HTTP 500.
- TP1/TP2/SL lifecycle updates are committed from the refresh path so stats-only reads do not lose state changes.
- Concurrent duplicate module-record inserts recover from a unique-index race.
- The existing live-only History version marker is preserved; this patch does not introduce another destructive cleanup.

Deployment: none. GitHub/Railway are not modified by this package.
