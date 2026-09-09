# XAUUSD AI Multi-Engine — TradingView-style Red Neon

Railway-ready XAUUSD analyzer combining:

1. **SIMPLE TRADING Book v1** deterministic pattern engine.
2. **Secondary 10-strategy engine** from the second uploaded analyzer.
3. **OpenAI second-opinion validator**.
4. **TradingView Lightweight Charts** frontend fed by real XAUUSD data from RealMarketAPI.
5. **RealMarketAPI WebSocket proxy** for live candle updates, with REST snapshot on initial load.
6. Candle countdown timer for the selected timeframe.

## Final signal logic

- Book + Secondary + OpenAI agree on BUY/SELL -> `CONFIRMED`.
- One deterministic engine is WAIT and the other deterministic engine + OpenAI agree -> engine-confirmed status.
- Conflicts -> `WAIT`.

## Environment variables

```env
REALMARKET_API_KEY=
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.6-luna
```

Keep both API keys server-side in Railway variables. Do not put them in frontend JavaScript.

## Deploy on Railway

The project uses the included `Dockerfile` and `railway.toml`.

1. Create/import this repository in Railway.
2. Add the three environment variables above.
3. Deploy.
4. Generate a Railway public domain.

## GitHub

Push the ZIP contents to a GitHub repository, then connect that repository to Railway. The application is self-contained and does not require a user's computer to stay online.

## Live data

The browser connects only to the app's `/ws/price` endpoint. The backend proxies the RealMarketAPI WebSocket so the API key never reaches the browser. REST is used for the initial candle snapshot and full analysis.

## Notes

The chart is based on TradingView's Lightweight Charts library; it is not the hosted TradingView.com chart widget. The chart itself remains a candlestick chart; the surrounding UI uses the red-neon/liquid-glass theme.

RealMarketAPI WebSocket availability and timeframe availability depend on the user's RealMarketAPI plan. If WebSocket access is unavailable, the app should use the REST snapshot/analysis path instead of exposing the API key.
