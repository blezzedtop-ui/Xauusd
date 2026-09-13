# XAUUSD live analysis build

## Current behavior
- TradingView `OANDA:XAUUSD` is the canonical chart/market-data source for analysis.
- Analysis candle data is read from the TradingView chart series; legacy RealMarket/Twelve Data keys are not used by `get_candles`.
- Economic Calendar is embedded directly from TradingView; no user calendar API key is required.
- Railway health check is `/api/health`.
- AI Smart Analysis has been removed from the main navigation/UI. Its old backend endpoint may remain for compatibility but is no longer loaded by the dashboard.
- Signal History stores module/source separately: Classic Trade, SNR, Signal Lab, ICT Signals and Signals.
- Module history is de-duplicated by user + module + timeframe + candle.
- Signal History analytics includes overall Win Rate and per-module Win Rate.
- Classic Trade evaluates the last completed candle instead of the still-forming candle.
- SNR signals now include entry/SL/TP values so they can be evaluated in history.

Actual broker order execution is NOT performed. History is paper/signal mode.
