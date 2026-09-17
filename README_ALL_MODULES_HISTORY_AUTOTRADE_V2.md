# SignalX — All Modules History + AutoTrade V2

## Applied rules
1. BUY: if R1/first TP is at or below Entry, it is not accepted as TP; the next valid structural resistance (R2/R3, module resistance/extension, then recent swing high) is searched.
2. SELL: if S1/first TP is at or above Entry, the next valid structural support is searched.
3. If no valid target exists, the module signal is preserved in Signal History as `WAIT` / `TARGET_REACHED` and is not sent to MT5.
4. Invalid Entry/SL/TP geometry can never become `TP2 HIT`.
5. Malformed historical rows are migrated to `CANCELLED` with `INVALID_LEVEL_GEOMETRY`; `profit_loss` and `r_multiple` are cleared.
6. Each module has its own History row and AutoTrade queue key for supported non-M1 timeframes.
7. M1 is always blocked from AutoTrade.
8. Book + OpenAI remains excluded from AutoTrade, while History recording is not globally blocked by that exclusion.
9. AutoTrade remains XAU/USD-only and uses the existing Real/Demo MT5 EAs; no EA replacement is required by this backend change.

## Module pipeline
Signal Lab, Signals, Technical Analysis, Classic Trade, SNR, Auto Trend Line, ICT Signals, AI Smart Analysis, and AlgoTrade are persisted independently when they produce a tradable BUY/SELL candidate.

## Validation
Python syntax checked with `py_compile` for `main.py`, `algotrade_strategy.py`, and `mt5_account_gateway.py`.
