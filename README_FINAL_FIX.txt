SIGNALX MT5 FINAL FIX
=====================

Fixed:
1. MQL5 compile error "arrays are passed by reference only" in AppendMarketState().
2. SL/TP validation for BUY/SELL with broker stop/freeze distance.
3. XAUUSD/EURUSD symbol routing.
4. Account state reporting: balance/equity/free margin/margin/positions.
5. Railway state endpoint is included in main.py with canonical symbol mapping.
6. BridgeToken is intentionally blank in source; enter the same secret as Railway MT5_BRIDGE_TOKEN in EA Inputs.

MT5:
- Copy mt5/SignalX_Dual_Symbol_EA.mq5 to MQL5/Experts.
- Compile with F7.
- WebRequest: https://signalx.asia
- Inputs BridgeToken = exact Railway MT5_BRIDGE_TOKEN.
- XAUTradeSymbol = your broker's XAU symbol (e.g. XAUUSDm).
- EURTradeSymbol = your broker's EUR symbol (e.g. EURUSDm).

After compiling, attach the EA to one chart only; the EA routes both configured symbols.
