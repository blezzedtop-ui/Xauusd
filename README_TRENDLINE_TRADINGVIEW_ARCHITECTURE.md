# Trend Line + Fibonacci / TradingView OANDA architecture

- The Auto Trend Line section contains exactly one chart: TradingView Advanced Chart with `OANDA:XAUUSD`.
- Changing M5/M15/M30/H1/H4/D1 remounts that TradingView chart with the selected interval.
- Backend Trend Line and Fibonacci calculations remain strictly per-timeframe and are not mixed between intervals.
- The previous separate LightweightCharts overlay chart has been removed.
- TradingView's embedded Advanced Chart is an isolated iframe; custom backend trendline/Fibonacci drawings cannot be programmatically injected into that widget through the public embed configuration. Therefore the dashboard keeps the calculated Trend Line/Fibonacci values and signals alongside the official TradingView chart rather than pretending the drawings are native TradingView drawings.
