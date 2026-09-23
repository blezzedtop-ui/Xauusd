# SignalX AutoTrade Worker — Always-On Toggle Fix

## What changed
The AutoTrade worker now starts on every Railway application startup instead of only when `MT5_AUTO_TRADING=true` at startup.

The worker checks the live AutoTrade flag on every cycle:
- OFF → idle; no signals are generated/queued.
- ON → signal generation/queueing resumes automatically.
- No Railway redeploy is required when switching AutoTrade OFF/ON from the site.

## MT5 side
The existing EA is unchanged. MT5 Terminal AutoTrading, EA permissions, and WebRequest settings must still be enabled for actual broker execution.
