# SignalX — All Active Modules → Signal History → MT5 AutoTrade V3

## Active signal families
- Signal Engine
- Technical Analysis
- Classic Trade
- Auto Trend Line
- ICT Signals
- AI Smart Analysis
- MSAI/SNR
- SMC
- Algo/SMC
- Patterns
- Trend Channel Engine
- Fibonacci
- Yangi Strategiya

## Retired / excluded
- Signal Lab
- AlgoTrade
- Book + OpenAI
- M1 / 1min / 1m for MT5 execution

Retired sources are blocked at module-record time and are excluded from Signal History V2 queries.

## History flow
Every active module that produces a deterministic BUY/SELL candidate is processed independently on the same canonical live candle series. The common pipeline stores a module-specific History row even when AI rejects execution.

`Module → AI/Market Quality → Geometry → Target → Risk → History`

## MT5 AutoTrade flow
Only eligible active signals reach the queue:

`Module → AI/Market Quality → Geometry → Target → Risk → RR >= 1.50 → MT5 Queue`

M1 is permanently blocked. Non-XAUUSD is blocked. Retired modules are blocked. Queue de-duplication remains keyed by market/source/timeframe/candle/direction.

## Yangi Strategiya
The Yangi Strategiya endpoint is the independent all-book fusion over the 32 supplied unique sources. It combines the existing strategy families and applies one final AI validation step. It is also a first-class active source in the live History/AutoTrade pipeline.

## Canonical data
All module candidates in the auto-record pipeline consume the same live TradingView candle series per timeframe, preventing cross-symbol/cross-timeframe mixing.
