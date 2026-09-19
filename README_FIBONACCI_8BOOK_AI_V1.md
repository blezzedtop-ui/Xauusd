# SignalX Fibonacci — 8 Book + AI Strategy V1

This module is an independent strategy family named **Fibonacci**. It does not replace ICT, SMC, Algo/SMC, MSAI/SNR or Trend Channel Engine.

## Source books

25. Fibo Musang Final BOBI / Home Course
26. Fibo Musang Elite — Fibo Setting & Cara Kerja Fibo
27. Fibonacci for the Active Trader
28. The Advanced Guide to Fibonacci Trading
29. Fibonacci Trading: How to Master the Time and Price Advantage
30. Fibonachchi Darajalari — 2-qism
31. Rahsia Fibo Musang 2011–2015
32. The Most Powerful Setup of Fibo Musang — 6 recurring setups

## Deterministic strategy

1. Detect a meaningful swing and market direction (HH/HL or LH/LL).
2. Build standard Fibonacci retracement levels: 23.6%, 38.2%, 50%, 61.8%, 78.6%.
3. Build extension references: 1.272, 1.618, 2.618, 4.236.
4. Compare multiple relevant swings and look for overlapping Fibonacci relationships / FibZone-style clustering.
5. Test horizontal S/R and trendline confluence.
6. Detect 50% Pin Bar / price-action reaction as confirmation.
7. Detect Fibo Musang context: Dominant Candle Break or nearest S/R/CB1-style break, then look for a retest-oriented context and 261/423 cycle references.
8. Apply a volatility/data-quality guard; extreme volatility without strong confluence returns WAIT.
9. Calculate entry, swing-based invalidation and extension targets; RR must be >= 1.50 for a deterministic trade candidate.
10. The live AI layer validates only the deterministic evidence. It may not invent prices, levels, news or strategy components.

## AI gate

Final BUY/SELL requires:

- deterministic signal is BUY/SELL;
- live AI validation is available;
- AI direction matches deterministic direction;
- AI confidence >= 85;
- AI agreement >= 70.

Otherwise the result is WAIT / WAIT_AI_VALIDATION.

## Cross-module routing

Useful Fibonacci concepts are exposed to:

- Technical Analysis — retracement/extension, FibZone, Fibo Musang and volatility context.
- Trend Line / Trend Channel — Fibonacci + trendline/SR confluence.
- Patterns — 50% Pin Bar, CBR/Initial Break/Dominant Candle setup context.
- Multi-Timeframe — higher-timeframe swing and Fibonacci context.
- Risk Engine — swing invalidation, extension targets and RR gate.
- Yangi Strategiya — Fibonacci becomes a dedicated consensus component alongside ICT Core, Algo/SMC, SMC, MSAI/SNR and Trend Channel.

## Data integrity

Forex broker candle differences can affect Fibonacci anchors during volatility. SignalX uses its canonical TradingView/OANDA candle series for this engine; when the data quality is insufficient, the engine returns WAIT rather than inventing a level.

## Route

`GET /api/v1/fibonacci/{symbol}?interval=5min`
