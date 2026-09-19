# SIGNALX — ALGO/SMC + AI v1.0

This module is derived from the supplied 232-page Algo/SMC trading book. It keeps the source terminology and sequencing where the book provides it:

- Liquidity-first analysis; Major / Medium / Minor liquidity
- Previous Daily / Weekly / Monthly / Yearly high-low liquidity
- Daily Cycle: Asia → London → New York; Asia liquidity; trap / real move framing
- 90-minute cycle anchored to New York midnight
- Weekly cycle narrative (Monday–Friday)
- Liquidity build-up → grab → reversal / continuation
- Money Transfer between sell-side and buy-side liquidity
- Algo Market Structure; Strong / Weak High-Low
- Fake Break in Market Structure / fake Momentum Shift filter
- Premium / Discount
- AMD: Accumulation → Manipulation → Distribution
- Institutional Order Flow / Algo Candle
- FVG / inefficiency / displacement / High Volume Imbalance
- Order Block / Breaker Block / Rejection Block concepts
- Top-down / multi-timeframe context
- Previous-candle liquidity and Ping-Pong timing concepts

## AI role

AI is a **strict validation layer**. It does not invent market data or create a trade from nothing. The deterministic engine must first produce a complete setup. Only then can AI confirm it.

For Algo/SMC:

- AI provider unavailable → WAIT
- AI direction differs from deterministic direction → WAIT
- AI confidence < 85 → WAIT
- AI agreement < 70 → WAIT
- AI validation is false → WAIT
- deterministic RR < 1.50 → WAIT

These numeric thresholds are SignalX implementation choices; they are not claimed to be values specified by the source book.

## Approximation notes

Some book concepts are descriptive rather than fully formalized mathematically (for example exact session clock boundaries, precise TDI formula/settings, and exact definitions for some block variants). Where the book does not give an executable formula, the implementation uses a clearly named heuristic/proxy and does not claim it is the book's exact algorithm.

## Endpoint

`GET /api/v1/algo-smc/{symbol}?interval=5min`

## UI

The new sidebar section is **Algo/SMC** and exposes:

- Final decision and strict AI gate
- Liquidity hierarchy and sweep
- AMD / weekly / 90m context
- Money transfer
- BOS / CHoCH / Strong H-L / Fake BMS
- Algo Candle / FVG / Displacement / OB / Breaker / Rejection Block / HVI
- Entry module
- Top-down MTF matrix
- Safety rules
