# Removed Signal Modules — 2026-09-19

The following modules are fully removed from the SignalX UI and signal pipeline:

- Signal Lab
- AlgoTrade
- Book + OpenAI

Changes:
- Navigation entries and dedicated UI sections removed.
- Book + OpenAI frontend calls and backend endpoint removed.
- Signal Lab dedicated advanced endpoint/save route removed.
- AlgoTrade router/module removed from the FastAPI app.
- AutoTrade candidate generation excludes all three retired sources.
- Module-history recording rejects the retired sources.
- Signal History hides legacy rows from the retired sources in list/stat APIs.
- MT5 EA also blocks the retired sources as a defense-in-depth measure.

Remaining active strategy families continue to operate independently.

## 2026-09-19 Signals / Signal Engine retirement
- The visible Signal Engine/Signals section is removed from the web UI.
- Signal Engine and generic Signals sources are excluded from the AutoTrade queue.
- Signal Engine is also removed from the AutoTrade consensus vote.
- Underlying API functions remain only for backward compatibility and are not part of the AutoTrade pipeline.
