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
