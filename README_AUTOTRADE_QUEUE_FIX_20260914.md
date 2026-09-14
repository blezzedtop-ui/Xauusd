# SIGNALX PRO — AUTO TRADE QUEUE FIX

This build fixes the signal-to-MT5 queue path.

- Every eligible BUY/SELL module signal is enqueued directly when recorded.
- The background worker also evaluates XAU/USD and EUR/USD continuously.
- Book + OpenAI is excluded.
- XAU/USD and EUR/USD are hard-separated in the queue and MT5 polling.
- Entry/SL/TP are revalidated against fresh live candles before enqueue.
- Duplicate queue entries are suppressed by market/source/timeframe/candle/direction.
- The dual-symbol MQL5 EA is included at mt5/SignalX_Dual_Symbol_EA.mq5.
