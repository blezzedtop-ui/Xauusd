# TradingView-only market data

This build uses **TradingView OANDA:XAUUSD as the single market-data source** for the chart, live price, OHLC candles, pivots, multi-timeframe analysis, Book patterns, advanced signals, and OpenAI context.

## Runtime data flow

TradingView chart / OANDA:XAUUSD
→ TradingView chart WebSocket OHLC series
→ FastAPI canonical candle feed
→ Pivot / technical / Book / multi-timeframe / signal calculations
→ OpenAI second opinion (uses only those TradingView candles)

The dashboard price is taken from the **same TradingView chart series latest close**, not from RealMarketAPI, Twelve Data, Yahoo, or another broker feed.

### Important
- `REALMARKET_API_KEY`, `TWELVE_DATA_API_KEY`, and Yahoo are **not used for market candles/price/analysis in this build**.
- They may remain in Railway variables for other unrelated legacy features, but market analysis does not call them.
- If TradingView is unavailable, the market-data endpoints return an explicit error/WAIT instead of silently substituting old/provider data.
- The embedded TradingView chart remains `OANDA:XAUUSD`.

### TradingView WebSocket
The backend reads the chart series from TradingView's chart WebSocket endpoint and uses the same symbol/resolution for analysis. The implementation handles TradingView's `~m~...` message framing, chart sessions, `resolve_symbol`, `create_series`, `timescale_update`, and heartbeats.
