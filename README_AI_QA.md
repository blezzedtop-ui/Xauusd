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

## 2026-09-17 provider reliability fix
- AI Q&A now uses a dedicated provider order instead of the signal-validation score router.
- Groq retries `openai/gpt-oss-120b` then `openai/gpt-oss-20b`; both are current Groq production model IDs.
- Gemini retries the configured model, then `gemini-2.5-flash`, then `gemini-2.5-flash-lite`.
- `/api/v1/ai/qa/status` exposes only non-secret readiness state to authenticated users.
- The UI checks provider readiness before submitting a question and shows a clear configuration error instead of silently presenting a generic fallback.
- No AutoTrade/Signal Engine/History/MT5 execution rules are changed by this fix.
