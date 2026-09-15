# SignalX PRO — Security V3 + AI Architecture

## Security V3
- Process-local IP/route rate limiting with HTTP 429 + Retry-After.
- Request body size guard (default 1 MiB).
- Login brute-force lockout per IP + identity after repeated failures.
- Security headers: nosniff, frame deny, strict referrer policy, permissions policy, cross-origin resource policy, no-store API responses.
- CORS remains allow-list based for SignalX production/Railway origins.
- FastAPI docs/OpenAPI remain disabled unless `ENABLE_API_DOCS=true`.
- Admin-only diagnostics, AI-provider controls, AI analysis, signal engine, signals, and MT5 controls remain server-side protected.
- Bearer session tokens are hashed in the database and revocable.
- MT5 bridge endpoints require the configured bridge token.
- Trading calculations and Entry/SL/TP validation remain server-side.

## Admin / Free
- New registrations are `role=user` + `plan=free`.
- The owner/admin is `role=admin` + `plan=admin`.
- Admin UI is hidden client-side for ordinary users, but every protected backend endpoint also enforces `require_admin`.
- Free users do not receive the admin-only AI/Signal Engine/MT5 controls.
- Existing subscription records are preserved; this build does not remove the subscription system.

## AI network
Configured providers can include Groq, DeepSeek, Gemini, OpenRouter, Groq Qwen, OpenAI, Mistral, Cerebras, Cloudflare Workers AI, and Hugging Face.
The router scores configured/healthy providers and automatically falls through on timeout/rate-limit/provider failure.

AI is not decorative: the shared AI validation layer receives the same deterministic TradingView-derived context used by the strategy engine. Its advisory result is attached to strategy components and to module outputs such as SNR, Classic Trade, and Trend Line + Fibonacci.

AI is explicitly **advisory/validation only** for AutoTrade. AutoTrade continues to forward every BUY/SELL source except `Book + OpenAI`, without confidence/zone/AI/MTF quality gates, as previously specified.

## Strategy chain
`Live OHLC -> Market Regime -> Technical -> SNR -> Trend Line -> Fibonacci -> Liquidity -> Order Block -> FVG -> BOS/CHOCH -> ICT -> MTF Context -> AI Validation -> Final Signal -> MT5 AutoTrade`

Timeframes: `1min, 5min, 15min, 30min, 1h, 4h, 1day`.

1M and 5M use stricter microstructure/high-volatility confirmation profiles. Every timeframe is still independently calculated from its own live candle series.
