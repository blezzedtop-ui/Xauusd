# SignalX History Result + HTTP500 Fix V5

This package fixes only the Signal History read/status-refresh path while preserving the existing trading modules and MT5 account UI.

## Fixed
- History V2 GET no longer commits a read transaction; this removes an unnecessary failure point that can surface as HTTP 500.
- Added fail-safe `POST /api/v2/signal-history/refresh` lifecycle refresh endpoint.
- Outcome resolver safely handles tuple/list candle responses, malformed legacy payloads, invalid intervals and malformed candle rows.
- Outcome evaluation uses the signal candle timestamp and post-signal candles, then checks the latest live candle close so current-bar outcomes can resolve without waiting for a new bar.
- Final states remain terminal: `TP2 HIT`, `SL HIT`, `CANCELLED`.
- TP1 remains intermediate: `TP1 HIT`.
- Result price, P/L and R-multiple are returned to the UI.
- Frontend refreshes History outcomes before reading the journal and auto-refreshes every 30 seconds while History is open.
- List and stats requests use `Promise.allSettled`; a transient stats failure does not erase the visible journal.
- Failed history load keeps existing signal cards visible and shows a retry control instead of destroying the list.

## Preserved
- Existing Signal Engine and strategy modules.
- AlgoTrade.
- Existing AutoTrade and M1 block.
- Multi-Broker MT5 Gateway and account-level AutoTrade UI.
- AI Q&A and AI fallback network.
- Existing `railway.json` startup `uvicorn main:app --host 0.0.0.0 --port $PORT`.
- Existing XAU/USD -> broker-symbol routing.

## Not deployed
- No GitHub push.
- No Railway deployment.
