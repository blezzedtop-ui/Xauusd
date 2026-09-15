SignalX Signal History + AutoTrade Fix

FIX:
- Fixed a scope bug in auto_record_signals(): live_by_tf is now returned from the candidate loader and reused by process_symbol().
- Previously _strategic_pro_for_timeframe() referenced live_by_tf outside its scope, causing each timeframe to fail before SignalHistory was saved/queued.
- Reuses the same live candle snapshot for consensus, Strategic Pro and level validation.

TIMEFRAMES:
- 1M remains analysis/history only; AutoTrade blocked.
- 5M, 15M, 30M, 1H, 4H, 1D remain AutoTrade-eligible subject to Strategic Pro + consensus gates.

AUTOTRADE:
- MT5_AUTO_TRADING must be true.
- AUTO_ENTRY_ENABLED must be true.
- EA/MT5 bridge must be connected and polling.
- execution_symbol remains XAUUSDm.

Verification after deployment:
- Signal History should start receiving Consensus rows for eligible timeframes when a setup passes all gates.
- Railway logs should show [AUTO TRADE WORKER] and [AUTO TRADE QUEUE] QUEUED lines when a setup passes.
- MT5 poll should return queued orders when the bridge is connected.
