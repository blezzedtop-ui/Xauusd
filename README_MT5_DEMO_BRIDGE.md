# Exness MT5 DEMO Bridge — PC setup

1. Run Exness MetaTrader 5 and log into the DEMO account.
2. In MT5: File -> Open Data Folder -> MQL5 -> Experts.
3. Copy `mt5_xauusd_bridge.mq5` into Experts.
4. Open MetaEditor, compile the file, and make sure there are no compile errors.
5. In MT5: Tools -> Options -> Expert Advisors -> enable WebRequest and add the Railway site URL, for example `https://xauusd-production-9fd9.up.railway.app`.
6. Attach the EA to the Exness gold chart. On the user's Exness account the symbol may be `XAUUSDm`; leaving `TradeSymbol` empty makes the EA trade the chart symbol automatically.
7. Set `ApiBase` to the Railway site URL and `BridgeToken` to the same value as Railway `MT5_BRIDGE_TOKEN`.
8. Keep MT5 Algo Trading enabled.
9. In the website, use the MT5 DEMO section, set lot size (start with 0.01), then enable AUTO ON.
10. Test only on DEMO first.

The website's MT5 Connect form records the intended demo account details; the actual authenticated trading connection is established by the running MT5 terminal + EA. The Railway backend does not store the trading password.


## Multi-symbol bridge
Use `mt5_xauusd_eurusd_bridge_final.mq5` for simultaneous XAUUSDm + EURUSDm state/candle reporting and Auto Trading. Attach it once; set ApiBase and BridgeToken, then ensure both symbols are available in Market Watch.
