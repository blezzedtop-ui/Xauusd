# XAUUSD V36 Railway FIX v4

## Important fix
RealMarketAPI `/api/v1/price` requires `symbolCode` AND `timeFrame`. The previous build omitted `timeFrame` for the quote request, causing HTTP 400 validation errors and preventing quote/analysis/signal modules from getting market data.

This build sends:
- symbolCode=XAUUSD
- timeFrame=M1
- apiKey from Railway `REALMARKET_API_KEY`

## Railway Variables
Set:
- `REALMARKET_API_KEY` = your RealMarketAPI secret key
- `MARKET_PROVIDER` = `auto`
- `ALLOW_DEMO` = `false`
- `SECRET_KEY` = a long random secret
- `DATABASE_URL` = Railway PostgreSQL reference if persistence is needed

Do not put the API key in frontend JavaScript or GitHub.

## Deploy
Replace the GitHub repository files with this ZIP's contents and let Railway redeploy.
Then open:
- `/api/health`
- `/api/market/diagnostics`

`/api/market/diagnostics` should show `realmarketapi.configured=true` and `ok=true`.
