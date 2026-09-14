# SIGNALX PRO — XAUUSD / EURUSD Master Design + Dual Auto Trade

## UI
- `index.html` is the master XAUUSD design.
- `eurusd.html` is rebuilt from the same master markup/CSS and uses EURUSD-specific symbol labels/data.
- Desktop layout is kept identical between the two pages.
- The existing responsive/mobile patches from the master are shared by both pages.

## EURUSD routing
The frontend now recognizes both `/eurusd` and `/eurusd.html` as the EURUSD page, so direct `.html` navigation no longer falls back to XAUUSD logic.

## Dual Auto Trade
The MetaTrader 5 section on both pages now has **AUTO TRADE MODE**:
- `BOTH SYMBOLS ON` = XAU/USD + EUR/USD auto-entry checks run from one active page.
- `SINGLE SYMBOL` = only the current page symbol is checked.
- The backend exposes `POST /api/v1/mt5/auto-dual?enabled=true|false`.
- `/api/v1/mt5/status` reports `auto_dual`.
- The frontend stores the selected dual-mode flag in same-origin localStorage so it is shared by XAUUSD and EURUSD pages.
- With dual mode ON, the queue can contain both symbols and the dual-symbol EA routes each order to its matching MT5 broker symbol.

## Auto-entry safety gates
The existing auto-entry rules remain in place: confidence threshold, strong-zone quality, AI confirmation, MTF alignment and duplicate/open-trade protections.

## Important
This project remains **DEMO-only** for MT5 bridge execution. The MQL5 source is included, but it was not compiled in this environment because MetaEditor/MetaEditor CLI was unavailable.
