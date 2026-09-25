# SignalX History — Persistent Journal

Signal History is now preserved across application upgrades and Railway redeploys.

Previous builds used a `HISTORY_LIVE_VERSION` migration that intentionally ran `DELETE FROM signal_history` once when the version changed. That behavior has been removed because it could make valid historical signals disappear from the journal.

Current behavior:

1. Existing `signal_history` rows are never cleared during startup.
2. The runtime migration marker is metadata only and is non-destructive.
3. A normal lookup index is used for `user + symbol + timeframe + module + live candle` so legacy rows are not deleted just to satisfy a uniqueness migration.
4. The application still prevents normal duplicate module records by checking the same live-candle identity before insert.
5. New History rows continue to come from the live signal pipeline and remain linked to the existing outcome/AutoTrade flow.

Note: records already deleted by an older deployed build can only be restored from an older database/backup if one exists.
