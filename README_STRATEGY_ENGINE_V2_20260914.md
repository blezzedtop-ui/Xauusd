# SIGNALX PRO — Strategy Engine V2

This build upgrades the existing modules without changing their routes/UI contracts:

- Technical Analysis: quantitative technical context + EMA/MACD/regime context.
- Classic Trade: adaptive regime-aware trend/pivot/SNR/candlestick decision.
- SNR: institutional-style strategy metadata and regime awareness while preserving existing SNR zone output.
- Auto Trend Line: existing confirmed-swing engine retained, with strategy/regime metadata exposed.
- Signals / Signal Lab: adaptive strategy quality layer with timeframe-specific selectivity, regime conflict checks, confirmation thresholds and decision state.
- AI Smart Analysis: richer server-side context is prepared for scenario-based reasoning; existing refresh/cache behavior is preserved.
- Book + OpenAI: existing independent second-opinion behavior remains isolated from AutoTrade.

Safety/compatibility rules preserved:
- XAUUSD and EURUSD remain symbol-isolated.
- MT5 AutoTrade queue remains limited to XAU/USD and EUR/USD.
- Book + OpenAI remains excluded from AutoTrade.
- Existing admin authentication, security headers, CORS and disabled production API docs remain intact.
- Existing routes and frontend field names are preserved; new fields are additive.

Validation performed:
- Python `py_compile` passed for `main.py`.
- Node `--check` passed for `app.js`.
- ZIP integrity checked with `unzip -t`.

Important: this is a deterministic strategy-engine upgrade, not a guarantee of profitability. Before enabling aggressive AutoTrade, validate the new filters with historical and out-of-sample testing.
