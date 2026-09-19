# SignalX Market Data Failover — 2026-09-19

SignalX now uses a shared market-data router for all strategy modules.

## Flow

`Market Data Router → canonical OHLC snapshot → deterministic strategy → AI validation → final signal`

For each symbol/timeframe the router tries the preferred provider first and automatically advances to the next available provider when a request fails. The default order is:

1. TradingView
2. RealMarketAPI
3. Twelve Data
4. Yahoo Finance

A provider is placed on a short per-provider cooldown after failure. A successful provider is immediately marked ONLINE. The selected snapshot is cached briefly by symbol + timeframe so all modules use identical OHLC/current-price input.

## Modules covered

Technical Analysis, AI Smart Analysis context, Classic Trade, MSAI Strategy, SMC, Algo/SMC, Trend Line Engine, Trend Channel Engine, Fibonacci, New Strategy, Patterns, ICT/advanced modules and Multi-Timeframe calculations inherit the shared `get_candles()` path.

## AI remains independent

The existing multi-provider AI router remains separate from market data. An AI provider failure causes automatic provider failover without changing the market snapshot.

## Important

Yahoo Finance is a fallback only. Its XAU/USD fallback uses GC=F futures data and can differ from spot XAU/USD, so the API response identifies the active provider and fallback warning. Paid/configured providers should be placed before Yahoo in production.
