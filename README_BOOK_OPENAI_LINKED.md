# XAUUSD — Book + OpenAI Linked Analysis

This is a patch of the existing working XAUUSD site. The existing site structure is preserved.

## What changed
- The chart is now TradingView Lightweight Charts using the site's own `/api/v1/candles/XAU/USD` feed.
- The external OANDA TradingView embed is no longer used, so the chart and analysis do not use two different data feeds.
- The selected chart timeframe is the same timeframe sent to the Book + OpenAI analysis endpoint.
- The existing live WebSocket updates the same chart candle.
- The main Signal Engine now displays the Book + OpenAI consensus.
- OpenAI is only a second-opinion validator of the book-pattern result. It is instructed not to add other trading strategies.

## Analysis endpoint
`GET /api/v1/book-openai-analysis/XAU/USD?interval=5min`

The endpoint returns the same candle set used by the chart plus:
- `book.signal`
- `book.patterns`
- `openai.signal`
- `openai.confidence`
- `signal` (final consensus)
- entry / stop loss / take profit

Final signal rule:
- Book BUY + OpenAI BUY = BUY
- Book SELL + OpenAI SELL = SELL
- Any disagreement or WAIT = WAIT

## Railway variables
Set these in Railway Variables:
- `REALMARKET_API_KEY`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`

Do not commit API keys to GitHub.
