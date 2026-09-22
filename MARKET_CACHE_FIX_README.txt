SignalX MARKET CACHE / Trendline fix (2026-09-22)

Changed only main.py in the last root-level deploy ZIP.
- Market snapshot cache: ignore a valid but too-short cached series when a caller requests more bars (e.g. quote 80 -> strategy 260).
- TradingView candle cache: same history-length guard, including stale fallback.
- No market prices, strategy rules, RR, account logic or MT5 execution rules were changed.

Why: Trendline's 80 CLOSED bars requirement is not satisfied by a cached 80-bar response if the last bar remains open (79 closed). The strategy returns WAIT / INSUFFICIENT_CLOSED_CANDLES.

After deploy: inspect /api/v1/strategies/trendline again after a new closed M5 candle. If it still reports INSUFFICIENT_CLOSED_CANDLES, log counts (raw/closed for M5 and M30, provider, timestamps) inside strategy_service.evaluate; never bypass candle verification.

This ZIP passed Python syntax compilation. It has NOT been deployed or MT5/demo-tested; it is not a claim of successful live-market correction.
