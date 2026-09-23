# SignalX AI Q&A

This module adds a user-facing AI Q&A section without changing the existing SignalX strategy, Signal History, AutoTrade, MT5 Bridge, or Multi-Broker Gateway execution rules.

## Behavior
- Requires an authenticated SignalX session before submitting a question.
- Reuses the existing AI fallback network (`ai_json_completion`).
- Adds live market context: current quote, deterministic technical analysis, MTF state, and best-effort economic-calendar events.
- Never sends provider API keys to the browser.
- Uses a small per-user rate limit (`AI_QA_MAX_REQUESTS`, default 12 per `AI_QA_WINDOW_SECONDS`, default 300 seconds).
- Returns an explicit fallback when AI providers are unavailable; it does not fabricate live news or prices.
- AI Q&A does not place orders, change AutoTrade settings, or alter the existing signal queue.

## UI
The new `AI Q&A` navigation item provides suggested questions such as current XAUUSD trend, yesterday-vs-today context, economic news, and FOMC scenario analysis.
