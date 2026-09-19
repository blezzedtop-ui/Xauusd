# SIGNALX — SMC

SMC is a dedicated strategy module built from the uploaded 33-page Smart Money Concepts manual and an AI validation gate.

## Source-derived modules
- BOS / CHoCH market structure
- Liquidity: EQH / EQL and liquidity sweep concepts
- IDM / inducement
- Order Block (OB)
- Fair Value Gap (FVG)
- Point of Interest (POI)
- Session liquidity concepts
- HTF → LTF refinement
- Entry modules: IDM + CHoCH, IDM + FLIP, previous-candle liquidity removal, single-candle liquidity check
- Risk management / RR

## Signal flow
`HTF Story → Structure → Liquidity → POI → IDM → BOS/CHoCH → LTF Confirmation → Risk → AI Validation`

## AI rule
AI is a validator only. It receives deterministic SMC state and may confirm or reject the setup. It does not invent market data and it cannot override a hard WAIT.

The implementation threshold is AI confidence >= 75 plus deterministic hard-gate checks. This score is an internal setup-quality gate, not a win-rate claim.

## MTF refinement mapping
The manual shows examples such as M15 → M1 and H1 → M5. SignalX therefore exposes a practical mapping for the selected live timeframe; this mapping is an implementation choice, not a universal rule stated by the manual.

## Session note
The manual teaches session liquidity but does not define one universal clock schedule for every broker/feed. SignalX therefore surfaces a rolling session-liquidity proxy instead of claiming a broker-independent session clock.
