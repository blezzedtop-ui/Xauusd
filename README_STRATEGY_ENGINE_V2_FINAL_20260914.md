# SignalX Strategy Engine V2 — Final

- Every timeframe: 1min, 5min, 15min, 30min, 1h, 4h, 1day uses Strategy Engine V2.
- 1M: Microstructure Momentum + Liquidity V2.
- 5M: M5 Liquidity + Displacement V2.
- Higher timeframes use dedicated structure/regime profiles.
- Common chain: Live OHLC → Market Regime → Technical → SNR → Trend Line → Fibonacci → Liquidity → Order Block → FVG → BOS/CHOCH → ICT → MTF Context → AI Validation → Final Signal → MT5 AutoTrade.
- AutoTrade forwards every BUY/SELL source except Book + OpenAI, across all seven timeframes.
- WAIT is never an order.
- XAUUSDm and EURUSDm are the only EA execution symbols; suffixless fallback and generic symbol scanning were removed.
- Entry/SL/TP are revalidated against fresh candles for the exact symbol/timeframe before queueing.
