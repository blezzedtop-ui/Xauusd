# EURUSD separate dashboard

- `/` = XAUUSD
- `/eurusd` = EURUSD dedicated dashboard
- Frontend automatically changes the symbol and TradingView symbol based on the route.
- MT5 bridge state is now stored per symbol (`XAU/USD` and `EUR/USD`) so heartbeats/candles do not mix.
- Attach `mt5_xauusd_bridge_final.mq5` to `XAUUSDm` and another instance to `EURUSDm` (or your exact Exness symbol). Leave `TradeSymbol` blank so the chart symbol is used.
- The EA rejects queued orders when the queued instrument does not match the chart symbol, preventing accidental cross-symbol trades.
