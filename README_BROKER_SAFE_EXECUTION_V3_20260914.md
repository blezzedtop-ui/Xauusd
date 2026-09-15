# SignalX PRO — Broker-Safe Execution Layer V3

This layer does not change the strategy/analysis logic. It hardens the final MT5 execution path for ordinary legitimate signal-based trading.

## Execution protections
- Exact execution symbols only: `XAUUSDm` and `EURUSDm`.
- No suffixless symbol fallback or generic symbol scanning.
- `Book + OpenAI` is rejected again at the EA layer.
- Persistent duplicate/replay guard using MT5 terminal Global Variables per account/order ID.
- Fixed SignalX magic number for trade isolation.
- Broker volume min/max/step normalization.
- Live bid/ask and broker stop-distance validation for SL/TP.
- Synchronous order execution with result reporting.
- Invalid symbol, direction, volume, or levels are rejected instead of being sent.

## Strategy preservation
- Strategy Engine V2 remains active for `1min, 5min, 15min, 30min, 1h, 4h, 1day`.
- The common chain remains: Live OHLC → Market Regime → Technical → SNR → Trend Line → Fibonacci → Liquidity → Order Block → FVG → BOS/CHOCH → ICT → MTF Context → AI Validation → Final Signal → MT5 AutoTrade.
- AutoTrade continues to accept every BUY/SELL source except `Book + OpenAI`, with WAIT never becoming an order.
- XAUUSD and EURUSD remain isolated.

## Explicitly excluded behavior
SignalX does not implement or encourage arbitrage, latency exploitation, bonus abuse, front-running, broker-rule bypass, or other exploitative execution behavior.

## Verification note
Python/JavaScript/static package checks can be performed in this environment. Actual MetaEditor compilation and live broker order execution still require the user's MT5 terminal/broker environment.
