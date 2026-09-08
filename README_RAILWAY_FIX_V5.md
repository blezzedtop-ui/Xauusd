# XAUUSD Railway FIX v5

Fixes:
- Signal/analysis engine now receives enough recent candles (previous build only returned 10 for non-H1 timeframes).
- Pivot/Key Levels no longer fail completely when D1 is unavailable; it falls back to H1-derived levels, then Yahoo GC=F.
- Analysis can fall back to Yahoo GC=F if RealMarketAPI rejects a timeframe/plan request.
- Frontend displays backend errors instead of leaving Signal Engine / levels blank.

Railway variables:
- REALMARKET_API_KEY = your own RealMarketAPI key
- MARKET_PROVIDER = auto
- ALLOW_DEMO = false
- DATABASE_URL = reference to Postgres DATABASE_URL

Do not put the API key in GitHub or frontend code.
