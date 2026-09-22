# SignalX

XAUUSD dashboard with eight retained sections plus ICT, Fibonacci, SNR, Order Block, Trendline, Texnik Analysis and Classik Analysis (15 sections total). Only these seven isolated strategy sources can generate new signals; AI-approved signals use Signal History and the existing MT5 gateway.

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

## ICT, Fibonacci and SNR signal flow
The background worker independently scans closed candles for ICT (liquidity sweep → MSS → FVG retest), Fibonacci (swing → retracement → confirmation) and SNR (confirmed zones → bounce/retest). All candidates require structural SL, observed TP targets, fresh entry and RR >= 1.40. The AI fallback network must return an explicit approval (confidence >= 85 and agreement >= 70; SNR also requires STRONG zone quality). AI provider failures fail closed; deterministic candidates never execute alone. Each approved candle is recorded in Signal History once per source. MT5 AutoTrade defaults OFF and must be explicitly enabled by an admin; while ON, the bridge and account-scoped gateway allow ICT Signals, Fibonacci and SNR Analysis only. Use a demo account to test end-to-end before live deployment. See `ICT_INTEGRATION_UZ.md`, `FIBONACCI_INTEGRATION_UZ.md`, `SNR_INTEGRATION_UZ.md`.

## Market Gate / 24-7 token saving
The deterministic strategy layer may run continuously, but automated new-signal creation, AI validation/provider calls, and MT5 AutoTrade are blocked while the Market Gate is closed. The gate first checks the configured daily technical-maintenance window (`Asia/Tashkent`, default 02:00–03:00), then fresh MT5 symbol trading-session telemetry from the EA. When MT5 session telemetry is unavailable, the service uses a conservative weekend fallback. Closed-market provider calls are prevented at the shared AI router, so provider token usage is effectively zero during a closed gate.

The MT5 EAs report `SymbolInfoSessionTrade` session state in broker server time.

## Fibonacci Analysis

The Fibonacci module independently scans closed M15 candles plus H1/H4 bias, confirmed structural A→B swings, 0.500–0.618 retracement with a closed-candle bounce, and fixed 1.272/1.618 extension targets. A signal requires live-entry deviation and RR >= 1.40. Its AI confirmation is fail-closed and only approved setups are saved in Signal History. The same approved signal is placed in the existing MT5 queue if AutoTrade is enabled. Other strategy APIs remain 410 and their records are never forwarded. See `FIBONACCI_INTEGRATION_UZ.md`. Live broker/EA execution is not verified by synthetic tests.

## SNR Analysis

Isolated SNR Analysis uses confirmed clustered H1 pivots, H4/H1 directional bias, M15 context, closed M5 bounce or breakout/retest, and actual opposing SNR targets. Mandatory independent AI validation and 1.40 RR guard precede new Signal History writes. Only when explicitly enabled does MT5 receive SNR Analysis orders. The retired source `SNR` remains excluded. See `SNR_INTEGRATION_UZ.md`. Synthetic tests do not prove live broker execution or profitability.

## Order Block Analysis

An independent M15 confirmed-swing/BOS/displacement detector waits for a fresh OB first M5 rejection. The live validator rejects stale data, bad geometry, RR under 1.40, and missing independent AI approval. New history source and the MT5 source whitelist include only `Order Block Analysis` (not retired `Order Block`). See ORDER_BLOCK_INTEGRATION_UZ.md. Synthetic tests do not prove broker execution or profitability.

## Trendline Analysis

Independent closed-candle M5 confirmed-swing scanner + M30/H1/H4 gate: 3rd touch or breakout/first retest, observed H1 target and RR >= 1.40. Strict provider AI confirmation required before History or MT5 queue. New source `Trendline Analysis` is distinct from retired legacy `Auto Trend Line`. See TRENDLINE_INTEGRATION_UZ.md. Demo test required before any live use.

## Texnik Analysis

Independent H1 EMA50/200 trend + confirmed M15 support/resistance pivot + M5 closed engulfing/pin-bar, EMA50 and RSI14 analysis. The technical engine never invents entry, stop or TP: it uses fresh live price, the tested M15 pivot and the nearest observed H1 price target. RR must be >=1.40. AI approval is mandatory and fails closed, and every accepted closed candle is saved once per source in Signal History. MT5 queueing requires the administrator to enable Auto Trading; the gateway and both EA source filters allow only the six active names. Retired `Technical Analysis` remains blocked (new source is `Texnik Analysis`). Convergent technical/other-strategy setups with the same entry, SL and TP share a single MT5 queue slot. See `TEXNIK_INTEGRATION_UZ.md`. Synthetic tests are not live broker execution or financial performance evidence.

## Classik Analysis (new, legacy Classic Trade still disabled)

Independent closed-candle H4/H1/M30 trend alignment; confirmed H1 swing S/R pivot; M15 closed-body breakout followed by its first retest; M5 closed engulfing or pin-bar rejection. Stops are beyond the retest invalidation, and the TP is the nearest *observed* H1 opposing price. No invented target to force RR. RR >= 1.40 and <= 6, live quote freshness, AI validation, no conflicting evidence, and one History record per module+closed M5 candle. New routes `/api/v1/classik-analysis-live/XAU%2FUSD` and `/api/v1/classik-analysis/process` require admin. The existing aggregate `/api/v1/signals/auto-record` now includes seven active engines. MT5 queue and both EA source allowlists include `Classik Analysis` (not the retired `Classic Trade`), and matching orders across sources are deduplicated while preserving distinct History rows. Auto Trading remains OFF until enabled by admin. See `CLASSIK_INTEGRATION_UZ.md`. Synthetic tests do not establish live market profitability or broker execution.
