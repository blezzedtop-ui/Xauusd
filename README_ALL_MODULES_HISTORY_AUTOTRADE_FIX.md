# SignalX — All Modules -> Signal History + AutoTrade

Applied change (2026-09-17):

- Every confirmed BUY/SELL module signal for XAU/USD is persisted independently in Signal History.
- Every confirmed BUY/SELL module signal is independently queued for MT5 AutoTrade.
- M1 / 1m / 1min remains blocked from AutoTrade.
- Book + OpenAI remains excluded from AutoTrade.
- Module-level source names are preserved (Signal Lab, Signals, Technical Analysis, Classic Trade, SNR, Auto Trend Line, ICT Signals, AI Smart Analysis, AlgoTrade).
- Live Entry/SL/TP levels are normalized/validated before History + AutoTrade so invalid geometry is not forwarded.
- Module signals are no longer collapsed into a single consensus order in `/api/v1/signals/auto-record`.
- MT5 EA is not changed by this patch.

Validation:
- `python -m py_compile main.py algotrade_strategy.py mt5_account_gateway.py` -> OK
- No Railway deployment was performed.
