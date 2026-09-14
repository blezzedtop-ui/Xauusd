SignalX_Dual_Symbol_EA — FIXED

Compile:
1. Copy SignalX_Dual_Symbol_EA.mq5 to MT5/MQL5/Experts.
2. Open MetaEditor.
3. Open the EA and press F7.
4. Attach it to a chart after a successful compile.

Inputs:
ApiBase = https://signalx.asia
BridgeToken = the exact same value as Railway MT5_BRIDGE_TOKEN
XAUTradeSymbol = XAUUSDm
EURTradeSymbol = EURUSDm

WebRequest:
Tools -> Options -> Expert Advisors -> Allow WebRequest for listed URL
Add: https://signalx.asia

The compile error shown in the screenshot was fixed by passing the ENUM_TIMEFRAMES array by reference.
