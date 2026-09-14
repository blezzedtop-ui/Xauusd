# SIGNALX AUTO TRADE REAL FIX — 2026-09-14

This patch preserves the site UI/icon/section structure and fixes the MT5 execution path.

## Changes
- MT5 AUTO TRADING defaults to ON at server startup unless explicitly disabled by `MT5_AUTO_TRADING=false`.
- Dual-symbol AUTO mode defaults to ON unless explicitly disabled by `MT5_AUTO_DUAL=false`.
- Dual EA fixes the MQL5 uppercase conversion call (`StringToUpper`).
- Dual EA now re-checks the symbol after `SymbolSelect`, so XAUUSDm/EURUSDm can be selected automatically from Market Watch.
- Default EA ApiBase is `https://signalx.asia`; **BridgeToken must still be set to the exact Railway `MT5_BRIDGE_TOKEN` value**.

## MT5 setup
1. Attach `mt5/SignalX_Dual_Symbol_EA.mq5` to one chart.
2. Set `BridgeToken` to the Railway `MT5_BRIDGE_TOKEN`.
3. Add `https://signalx.asia` in MT5 Tools → Options → Expert Advisors → Allow WebRequest.
4. Make sure `XAUUSDm` and `EURUSDm` are visible in Market Watch (EA also attempts `SymbolSelect`).
5. Turn Algo Trading ON.

The site UI is not intentionally redesigned in this fix.
