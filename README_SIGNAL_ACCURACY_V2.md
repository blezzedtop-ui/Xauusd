# Signal Accuracy V2 (DEMO test build)

This build makes automatic entries more selective. It does not guarantee win rate or profitability.

## Main changes
- Signal Lab evaluates only the last completed candle, avoiding signals based on a still-forming candle.
- Deterministic Signal Lab threshold raised from score 6 to 8.
- BUY requires RSI >= 55 and bullish local + global trend.
- SELL requires RSI <= 45 and bearish local + global trend.
- Auto-entry default confidence threshold raised to 90.
- Auto-entry strong-zone minimum raised to 88.
- Auto-entry requires AI signal agreement with the deterministic direction, AI confidence >= 90, agreement >= 75, and no AI risk flags.
- Auto-entry requires first-target RR >= 1.50.
- Auto-entry requires higher-timeframe directional alignment when higher timeframes exist.
- Quality metadata exposes `quality_grade`, `confirmations`, and `risk_reward`.

## Railway variables
Optional; defaults are already conservative:
- AUTO_ENTRY_THRESHOLD=90
- AUTO_ENTRY_MIN_ZONE=88
- AUTO_ENTRY_MIN_AI_AGREEMENT=75
- AUTO_ENTRY_MIN_RR=1.50
- AUTO_ENTRY_REQUIRE_MTF=true

For DEMO testing, keep MT5 demo account and do not use REAL mode.
