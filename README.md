# SignalX

Production-oriented XAUUSD trading analytics dashboard with TradingView market data, strategy modules, signal history, AI validation/failover, and MT5 gateway execution.

## Required Railway variables

Set these before deploying:

- `ADMIN_LOGIN`
- `ADMIN_PASSWORD` (12+ characters)
- `SECRET_KEY` (stable random secret; do not rotate on every deploy)
- `DATABASE_URL` (PostgreSQL recommended for production)

Configure AI/market/MT5 API keys only for providers and integrations you actually use. See `.env.example` for the supported variable names.

## Security notes

- No production SQLite database is shipped in the release archive.
- No admin password is embedded in source code.
- Session signing requires a stable `SECRET_KEY` from the environment.
- `__pycache__`, bytecode, backup files, and patch-note README files are excluded from the production container.
- MT5 account credentials are not stored by the current gateway UI; use the EA pairing flow.


## AI Router recovery
The AI router uses short transient cooldowns and a real-request recovery path for Groq/Gemini. Billing/auth/model errors are not retried until reset.

## AI token-saving mode
Signal generation is deterministic and can run continuously. Live AI validation is event-driven: the AutoTrade worker only calls AI when at least two independent strategy families form a consensus candidate on a closed candle and the deterministic pre-check reaches the configured confidence/RR threshold. One AI validation result is reused for all module signals in the same timeframe/candle, and a failed AI validation is cached for that candle to prevent repeated retries. AutoTrade remains blocked unless a live AI validation passes together with the geometry/risk gates and RR >= 1.40.

## Market Gate / 24-7 token saving
The deterministic strategy layer may run continuously, but automated new-signal creation, AI validation/provider calls, and MT5 AutoTrade are blocked while the Market Gate is closed. The gate first checks the configured daily technical-maintenance window (`Asia/Tashkent`, default 02:00–03:00), then fresh MT5 symbol trading-session telemetry from the EA. When MT5 session telemetry is unavailable, the service uses a conservative weekend fallback. Closed-market provider calls are prevented at the shared AI router, so provider token usage is effectively zero during a closed gate.

The MT5 EAs report `SymbolInfoSessionTrade` session state in broker server time.
