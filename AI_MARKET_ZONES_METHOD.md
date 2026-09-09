# AI Market Zones — XAU/USD

Pivot / Key Levels is now a real-market zone engine. It does not display fixed R3/R2/R1/Pivot/S1/S2/S3 as the primary UI.

The selected timeframe is primary. Zones are calculated from that timeframe's real OHLC candles using:
- swing highs/lows
- previous completed candle extremes
- rejection candles
- consolidation/range extremes
- FVG imbalance
- order block/displacement evidence
- liquidity/equal swing areas
- classic pivot levels only as secondary confirmation

Nearby prices are clustered into Demand/Support and Supply/Resistance zones. Strength is based on observed evidence, touches and recency.

OpenAI ranks and labels only the existing real-OHLC candidates. It cannot invent, move, or replace zone prices. If AI is unavailable, the same real-data zone engine remains available in rule-based mode.

The UI shows the selected timeframe's zones and AI bias/scenario. Switching timeframe triggers a fresh zone calculation for that timeframe.
