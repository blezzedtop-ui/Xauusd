# SignalX MT5 AutoTrade V4 — 2026-09-15

## Fix
- Added per-terminal `client_id` to MT5 polling/reporting.
- Added short claim leases so a crashed terminal cannot permanently hold a signal.
- XAU/USD and EUR/USD remain hard-separated at transport and EA execution layers.
- Successful orders are removed from the queue; failed orders are released for retry.
- EA client id defaults to the MT5 account login (`SignalX-<login>`).
- EA still executes only `XAUUSDm` and `EURUSDm`.

## MT5
1. Compile `mt5/SignalX_Dual_Symbol_EA.mq5` in MetaEditor.
2. Attach it to an active chart.
3. Enable AutoTrading in MT5.
4. Add `https://signalx.asia` under Tools -> Options -> Expert Advisors -> Allow WebRequest.
5. Keep the EA running while testing.
