# SIGNALX PRO — Real Live Auto Trade Fix (2026-09-14)

This build keeps the existing XAUUSD master layout, EURUSD page structure, sidebar and icons unchanged.

## Execution/data rules
- XAUUSD and EURUSD are isolated end-to-end by canonical symbol key.
- Signal/analysis paths use fresh TradingView candles and do not fall back to stale cached candles when a fresh fetch fails.
- The active/latest TradingView candle is used for current signal calculations, so Entry/SL/TP are derived from the current chart series rather than an older snapshot.
- AUTO TRADE forwards BUY/SELL signals from all enabled non-Book/OpenAI sources without confidence, zone-quality, AI-agreement or MTF execution gates.
- Before queueing, Entry/SL/TP are revalidated against fresh candles for that exact symbol/timeframe. Invalid or stale levels are repaired from the same live chart structure.
- Module-history recording also revalidates levels server-side from live candles, preventing client-side stale levels from being stored.
- MT5 polling keeps symbol in the order payload; the Dual Symbol EA routes EURUSD orders to EURTradeSymbol and XAUUSD orders to XAUTradeSymbol.
- MQL5 dual EA uses StringToUpper correctly.

## Verification
- Python AST / compile: PASS
- JavaScript syntax: PASS
- 10 repeated invariant verification rounds: PASS
- Synthetic directional Entry/SL/TP validation (BUY): PASS
- Synthetic directional Entry/SL/TP validation (SELL): PASS
- ZIP critical-file integrity: PASS

## MT5 note
MetaEditor/MQL5 compiler is not installed in the build environment, so the EA is statically validated but not compiler-verified here. Compile `mt5/SignalX_Dual_Symbol_EA.mq5` in MetaEditor before attaching it to MT5.
