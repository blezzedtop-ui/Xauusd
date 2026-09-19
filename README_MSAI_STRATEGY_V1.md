# SIGNALX — MSAI STRATEGY v1.0

This release replaces the standalone SNR dashboard page with a single execution page built from the uploaded Malaysian SNR manual.

## Core layers

1. HTF Storyline / MTF
2. Malaysian SNR: body Open/Close transitions
3. Fresh/Unfresh SNR, Touch/Rejection and MISS
4. Liquidity Sweep
5. Engulfing / Flipped Engulfing
6. SNR + Trendline confluence
7. QML / HNS structure
8. LTF Breakout + Retest / 2-TF confirmation
9. Roadblock / RR execution checks
10. AI validation gate

## Hard gate

`NO VALIDATION -> NO TRADE`

Final BUY/SELL requires deterministic MSAI confirmation and a matching live AI validation response. When the AI provider is unavailable or does not confirm the deterministic direction, the UI stays on WAIT.

## API

`GET /api/v1/msai-strategy/{symbol}?interval=5min`

The endpoint returns the final decision, score, AI state, MTF storyline, SNR/price-action components, two-timeframe confirmation, execution levels and active session context.

## Source basis

The strategy terminology and flow are based on the uploaded `Trading SNR the Malaysian Way` manual. The numeric score and RR >= 1.5 implementation threshold are SignalX engineering rules, not claims that the manual specifies those exact numbers.
