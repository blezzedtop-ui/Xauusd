# SignalX Pattern AI Strategy P1

Pattern Engine is a first-class XAU/USD signal source. Pattern detection is deterministic; AI validates the detected setup before AutoTrade.

## Pattern families
- Reversal: Double/Triple Top & Bottom, Head & Shoulders, Inverse Head & Shoulders, Diamond, Rounding.
- Continuation: Bullish/Bearish Flag, Pennant, Rectangle, Cup & Handle.
- Breakout/bilateral: Ascending, Descending, Symmetrical Triangle, Rising/Falling Wedge.

## Flow
OHLC -> Swing High/Low -> Pattern Detector -> Breakout Confirmation -> Pattern Score -> AI Validation -> MTF Alignment -> Geometry -> TP1 -> Risk -> MT5 AutoTrade.

## Gates
- Bilateral patterns do not guess a direction before breakout.
- Pattern score uses structure 35, breakout 20, MTF 20, S/R context 10, candle confirmation 10, session 5.
- Strong signal threshold: pattern score >= 85, confirmed breakout, MTF aligned, and AI agrees when a live AI provider is available.
- AI provider outage falls back to deterministic validation; the UI labels the mode.
- TP1 is primary. TP2 is optional/informational.
- RR is informational only and is not an AutoTrade gate.
- M1 remains analysis/history-only and is blocked from AutoTrade.

## AutoTrade
Pattern BUY/SELL candidates are inserted into the same Signal History and MT5 queue pipeline as other eligible modules. The existing execution gate independently checks level geometry, valid TP1 and SL risk.
