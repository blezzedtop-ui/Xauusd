# SignalX Multi-Broker MT5 Gateway — FIXED package

This package is based on the SignalX V10 application and adds the MT5 Account Gateway without replacing the existing Railway startup command.

## Safety fixes included

- `railway.json` remains `uvicorn main:app --host 0.0.0.0 --port $PORT`.
- No separate launcher is required for production startup.
- `main.py` registers the gateway router directly after the core application/models are loaded.
- Gateway tables are explicitly created after gateway models are registered: `mt5_accounts`, `mt5_pairings`, `mt5_account_symbols`, `mt5_gateway_orders`.
- SQLite/PostgreSQL timezone values are normalized before datetime comparisons.
- MT5 account AutoTrade remains OFF by default after pairing.
- M1 is blocked from the core AutoTrade queue and again blocked by the gateway sync layer.
- Canonical `XAU/USD` is mapped to the broker-specific symbol discovered by the EA, including common suffix/prefix variants.
- EA reports `FILLED` only when an MT5 deal ticket exists; otherwise an accepted order is reported as `SENT`.
- Existing SignalX V10 signal engine, History, and AutoTrade logic are retained as the base rather than replaced by a new launcher.

## Production deployment

Do **not** replace the existing `railway.json` with an alternate launcher configuration. Deploy this package as the complete application only after the owner reviews the diff and performs the final Railway backup/deployment step.

## EA

MetaEditor/MQL5 compiler was not available in the build environment used for this package. Python/application integration was tested, and the EA was structurally checked. Before live use, compile `mt5/SignalX_MultiBroker_Gateway_EA.mq5` in MetaEditor and confirm zero compiler errors.
