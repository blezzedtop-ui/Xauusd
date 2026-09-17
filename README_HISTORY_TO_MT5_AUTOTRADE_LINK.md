# SignalX — Signal History → MT5 AutoTrade Link

This patch keeps Signal History as the persistent record and adds a safe bridge from newly-created eligible History records to the existing MT5 AutoTrade queue.

Rules:
- XAU/USD only for the existing MT5 execution boundary.
- M1/1m/1min is always blocked.
- BUY/SELL only.
- ACTIVE signals only.
- Book + OpenAI is excluded.
- Entry, SL and at least one TP are required.
- Existing queue de-duplication is reused.
- Only records created after the current process start are scanned by the background bridge, preventing old historical rows from being replayed after deployment/restart.
- Existing direct AutoTrade paths remain compatible; duplicate queue entries are suppressed by the existing queue key.

No production deployment is performed by this package.
