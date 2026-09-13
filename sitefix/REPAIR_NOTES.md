# XAU/USD — Stable Dashboard Repair

This build keeps the TradingView Advanced Chart and repairs the dashboard architecture:

- Navigation works without forcing a login modal.
- TradingView chart mounts independently from backend analysis.
- Technical Analysis, Pivot/Key Levels, Signal Lab, Signals and MTF use the same live backend candle/quote feed.
- Guest users can view market analysis and live signals; authentication is required only to save/journal signals and view private history/statistics.
- Startup is isolated: one failed API module cannot disable the rest of the UI.
- Expensive 7-timeframe modules are briefly cached to prevent provider request bursts.
- Timeframe buttons no longer trigger duplicate handlers.
- Logout no longer blocks the whole dashboard with the login modal.
- No demo data is enabled; REALMARKET_API_KEY remains the primary live provider.

Railway: deploy this ZIP's files to the existing `blezzedtop-ui/Xauusd` service and keep the existing real API variables.
