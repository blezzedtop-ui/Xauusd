# SignalX Book Engines V1 — 2026-09-19

## Strategy families

### Trend Channel Engine
Independent strategy family built from the six trend-focused books supplied after the ICT set:
1. Trendline Savdo Strategiyasi — Sirlarni Tekshirish
2. Trend chiziqlari: ularni savdoda qanday foydalanish kerak?
3. Trend savdo qilish strategiyasi
4. Trend kanallari
5. Parabolic SAR
6. M&W Trendline Trading Strategy

Deterministic layer uses trend structure, valid trendlines, touch count, channel boundaries, breakout/retest, reversal price action, MTF, MA20/50/200, Parabolic SAR and risk/RR. AI is a separate strict validator.

Hard AI gate: live AI required, validation=true, direction agreement, confidence >= 85 and agreement >= 70.

### Yangi Strategiya
Independent all-book fusion over the 32 unique supplied book sources. It does not replace the individual MSAI/SNR, SMC, Algo/SMC, ICT or Trend Channel engines.

Deterministic fusion combines:
- ICT Core — 22%
- Algo/SMC — 18%
- SMC — 14%
- MSAI/SNR — 13%
- Trend Channel — 13%
- Fibonacci — 20%

The final direction also checks MTF alignment, consensus separation and RR >= 1.50 before the AI validator is allowed to confirm it.

## Routing

- ICT books: ICT section and ICT-specific context.
- SMC book: SMC section.
- Algo/SMC book: Algo/SMC section.
- Malaysian SNR book: MSAI/SNR section.
- Trendline/trend/channel/PSAR books: Trend Line, Technical Analysis and Trend Channel Engine.
- Cross-book MTF principles: Multi-Timeframe section.
- Cross-book context: Yangi Strategiya → All Books → Modules.

## Data integrity

COT, USDX, Open Interest, Interest Rates and Seasonality are displayed as `NOT_CONNECTED` until a real feed is wired. The system does not invent those values.

## New routes

- `GET /api/v1/trend-channel/{symbol}?interval=...`
- `GET /api/v1/new-strategy/{symbol}?interval=...`


### Fibonacci
Independent strategy family from books 25–32. Deterministic layer: swing selection, 23.6/38.2/50/61.8/78.6 retracements, 1.272/1.618/2.618/4.236 extensions, Fibonacci price clusters/FibZones, Fibo Musang CBR/Initial Break/Dominant Candle/nearest S/R break, 50% Pin Bar confirmation and volatility filtering. Final AI gate requires live validation, matching direction, confidence >= 85 and agreement >= 70.

## New route

- `GET /api/v1/fibonacci/{symbol}?interval=...`
