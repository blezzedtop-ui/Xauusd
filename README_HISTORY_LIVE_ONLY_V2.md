# SignalX History — Live Only V2

This build intentionally removes all legacy Signal History rows once, on first startup of version `live-only-2026-09-17-v3`. A persistent DB marker prevents the deletion from repeating on normal Railway restarts.

New uniqueness rule: one History row per `user + symbol + timeframe + module + live candle`. Direction is not part of the identity, so a live candle that flips BUY/SELL updates the same row instead of creating a duplicate.

New History rows are generated from the current/live signal pipeline only. No old archive is retained. AutoTrade and strategy execution logic are not intentionally changed by this History cleanup.
