# SignalX — Signal History V3 Fix

## Changes
- Database-level unique identity for module history signals:
  `user_id + symbol + interval + direction + source + candle_time`
- Legacy duplicate rows are repaired once at startup before the unique index is enforced.
- Duplicate requests return the existing canonical signal instead of creating/queueing another signal.
- TP1 is displayed as an intermediate state; TP2 is the final WIN state; SL is the final LOSS state.
- History cards now show an explicit result badge and final result field.
- Daily / Weekly / Monthly performance views are separated into UI tabs.
- Win Rate uses only final TP2 and SL outcomes.
- Existing strategy, AlgoTrade, AutoTrade, Multi-Broker MT5 and Railway startup architecture are preserved.

## Production safety
- This package is NO DEPLOY.
- Do not upload any local database file from this package to overwrite production data.
- MQL5 must still be compiled in MetaEditor before replacing the EA on an MT5 terminal.
