Final update

- XAUUSD and EURUSD have separate pages: / and /eurusd.
- EURUSD page uses OANDA:EURUSD for TradingView data where applicable and Exness MT5 EURUSDm for MT5 Trend/Fibonacci.
- MT5 backend stores symbol-separated markets and filters order queue by symbol.
- New EA: mt5_xauusd_eurusd_bridge_final.mq5 reports XAUUSDm + EURUSDm and polls Auto Trading orders.
- Auto Trading remains >=84.99% + Strong Zone + AI confirmation + MTF alignment.
- Live market-news banner restored.
- Auth login/register controls have direct fallbacks.
