# REAL CHART ANALYSIS V1

- The dashboard chart and analysis now use the same canonical `/api/v1/chart-analysis/{symbol}?interval=...` snapshot.
- Candles are real OHLC data from the configured live market provider.
- Pivot, support, resistance, MA20/MA50, RSI, MACD, Bollinger and ATR are calculated from the selected timeframe candles.
- Timeframe switching recalculates the entire analysis.
- The visible candlestick chart is rendered from the same backend candle array used by the analysis engine.
- The technical score is a 0-100 alignment score, not a win-rate/profit probability.
- No demo/generated candles are used by the chart-analysis endpoint.
