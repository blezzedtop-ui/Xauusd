# XAUUSD AI Multi-Engine — GitHub + Railway Ready

Real XAUUSD analysis dashboard using:
- RealMarketAPI for live/historical XAUUSD data
- TradingView Lightweight Charts for the candlestick chart
- SIMPLE TRADING Book v1 pattern engine
- Secondary 10-strategy price-action engine
- OpenAI second-opinion validator
- FastAPI backend + WebSocket proxy

## Railway Variables
Set these in Railway > Service > Variables. Never commit real keys to GitHub.

- `REALMARKET_API_KEY`
- `OPENAI_API_KEY`
- `OPENAI_MODEL` = `gpt-5.6-luna`

## Deploy from GitHub
1. Create an empty GitHub repository.
2. Upload the contents of this folder to the repository root. Do not upload the ZIP itself.
3. In Railway, create/select a service and connect that GitHub repository.
4. Railway detects `Dockerfile` and builds it automatically.
5. Add the variables above and redeploy.
6. Test `/api/health` and then open the generated Railway domain.

## Important
API keys stay server-side in Railway. The browser connects only to the FastAPI WebSocket/REST endpoints.

The chart is TradingView Lightweight Charts with RealMarketAPI data; it is not the hosted TradingView.com widget.
