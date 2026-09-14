SIGNALX MT5 ROUTING FIX

This version fixes cross-symbol auto-trade routing.
- EURUSD/EURUSDm/EUR/USD routes only to EURTradeSymbol.
- XAUUSD/XAUUSDm/XAUUSDc/XAUUSDr/XAU/USD routes only to XAUTradeSymbol.
- Unknown or missing symbols are rejected; the EA never falls back to the chart symbol.
- Backend queue includes explicit route_symbol.
- Backend canonical symbol mapping recognizes broker suffixes.

Compile mt5/SignalX_Dual_Symbol_EA.mq5 with F7.
