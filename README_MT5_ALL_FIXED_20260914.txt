SignalX MT5 + Railway — ALL FIXED

1) MT5 account state fix
- Broker suffixes such as XAUUSDm/XAUUSDc/XAUUSDr and EURUSDm are normalized to XAU/USD and EUR/USD.
- Balance, Equity, Free Margin, Margin and Positions are preserved in the Railway bridge state.

2) SL/TP execution fix
- EA validates SL/TP against the ACTUAL broker Bid/Ask at execution time.
- SYMBOL_TRADE_STOPS_LEVEL and FREEZE_LEVEL are respected.
- If a signal contains wrong-side/stale/too-close SL or TP, the EA rebuilds market-relative protective levels instead of sending invalid stops.
- Prices are normalized to the broker symbol digits.

3) Setup
- Copy mt5/SignalX_Dual_Symbol_EA.mq5 to MQL5/Experts and compile with F7.
- Inputs: ApiBase=https://signalx.asia; BridgeToken=the exact Railway MT5_BRIDGE_TOKEN; XAUTradeSymbol=XAUUSDm; EURTradeSymbol=EURUSDm.
- MT5 Tools > Options > Expert Advisors > Allow WebRequest: https://signalx.asia
- Algo Trading ON.
- In SignalX, press MT5 section Refresh after EA has sent a state heartbeat.
