SignalX XAUUSD — M5 Strategic Pro SP2

M5 AutoTrade is intentionally selective.

Chain:
H4 Bias -> H1 Bias -> M15 Bias -> London/NY Session -> Asian Liquidity -> Liquidity Sweep -> MSS/CHoCH -> Displacement -> OB/FVG Retest -> Volatility Filter -> RR Validation -> News Filter -> MT5 Spread Guard -> AutoTrade

Rules:
- M1 never enters AutoTrade.
- Only XAU/USD is eligible; execution symbol is XAUUSDm.
- M5 requires strategic confirmation to match consensus and score >= 85.
- London/New York session filter is enabled by default (env M5_SESSION_ONLY=true).
- Asian liquidity range is evaluated from UTC 00:00-08:00 M5 candles; matching sweep receives bonus points.
- Volatility filter blocks unusually dead or extreme M5 volatility. Defaults: ATR ratio 0.70-2.20.
- High-impact news blackout uses Trading Economics when TRADING_ECONOMICS_API_KEY exists, otherwise Finnhub when FINNHUB_API_KEY exists. If neither is configured, the filter fails open and does not block trading.
- EA blocks excessive live broker spread. Default MaxSpreadPoints=80; adjust to broker symbol digits/typical spread.
- SL remains structural: sweep extreme / OB with ATR buffer.
- TP uses liquidity target and minimum 1.5R; target can extend to 2.5R or beyond when structure allows.

Important:
These filters improve selectivity; they do not guarantee profitability. Backtest and forward-test before live money.
