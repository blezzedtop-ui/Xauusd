# Advanced Analysis Add-on

This package is built as an add-on to the existing working XAUUSD Price Action site. The original `/api/market`, `/api/ai-analysis`, chart, and widget flow are retained.

## Added endpoint
`GET /api/advanced-analysis?timeframe=M30`

## Analysis structure
1. SIMPLE TRADING Book v1 pattern engine:
   - Double Top
   - Double Bottom
   - Head & Shoulders
   - Inverse Head & Shoulders
   - Ascending Triangle
   - Descending Triangle
   - Symmetrical Triangle
   - Bullish Flag
   - Bearish Flag
   - Falling/Rising Wedge
2. Secondary 10-strategy engine already present in the working site.
3. Market structure: HH/HL/LH/LL and bullish/bearish/range state.
4. Support/resistance zones and pivot levels.
5. Deterministic final signal: BUY / SELL / WAIT.
6. Structure conflict can force WAIT instead of a counter-trend deterministic signal.

The book supports the reversal/pattern concepts such as Double Bottom and Double Top; numeric tolerances in code are implementation parameters, not claims that the PDF specifies those exact percentages.

## Important
The existing site is not replaced. This is an additive integration. If `REALMARKET_API_KEY` exists in Railway, the new advanced endpoint reads XAUUSD candles from RealMarketAPI. Otherwise it uses the existing Twelve Data source so the current working site remains compatible.
