# XAUUSD V36 Railway FIX

This build fixes two issues seen on phone/cloud deployment:
- TradingView chart was mounted while its mobile section was hidden; the chart is now mounted only after the section becomes visible.
- Yahoo fallback now uses GC=F as the gold futures proxy instead of the failing XAUUSD=X endpoint, and quote polling uses 5-minute candles.

For best XAUUSD spot accuracy, set REALMARKET_API_KEY in Railway Variables. If it is absent, the backend attempts the Yahoo GC=F fallback.

After replacing the GitHub files, Railway will redeploy automatically.
