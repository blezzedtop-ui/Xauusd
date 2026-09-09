# XAUUSD M30 — Railway + OpenAI

Bu loyiha lokal kompyuterda doimiy ishlab turishni talab qilmaydi.
Railway'ga bitta service sifatida deploy qilinadi.

## Ishlash zanjiri

Real XAU/USD market data
→ M30 OHLC
→ 10 ta Price Action strategy
→ pattern detection
→ BUY / SELL / NO TRADE
→ OpenAI validation
→ confidence / bias / support / resistance
→ Entry / SL / TP / R:R
→ web chart

## Railway Variables

Railway → Service → Variables ichiga:

```text
TWELVE_DATA_API_KEY=YOUR_MARKET_KEY
OPENAI_API_KEY=YOUR_OPENAI_KEY
OPENAI_MODEL=gpt-5.4
SYMBOL=XAU/USD
INTERVAL=30min
OUTPUTSIZE=300
POLL_SECONDS=15
AI_CACHE_SECONDS=45
```

API kalitlari kod ichiga yozilmagan. Railway Variables orqali beriladi.

## Deploy

1. Shu ZIP tarkibini GitHub repository'ga joylang.
2. Railway'da `New Project` → `Deploy from GitHub Repo`.
3. Repository'ni tanlang.
4. Railway Dockerfile'ni avtomatik ishlatadi.
5. Variables'ni kiriting.
6. Deploy tugagach Railway bergan domenni oching.

Kompyuter o'chirilgan bo'lsa ham sayt Railway serverida ishlayveradi.

## Muhim

- Bu loyiha savdoni avtomatik amalga oshirmaydi.
- Signal va tahlil faqat mavjud market OHLC ma'lumotlari asosida hisoblanadi.
- OpenAI ikkinchi tahlil/validatsiya qatlamidir.
- Chart TradingView Lightweight Charts kutubxonasida chiziladi.
- Market feed bu loyihada Twelve Data orqali olinadi; bu TradingView terminalining o'z broker feed'i emas.
- M30 data polling orqali yangilanadi. Tick-by-tick streaming uchun alohida WebSocket feed ulash kerak.

## Health check

`/api/health`

U yerda market-data va OpenAI key konfiguratsiyasi faqat `true/false` ko'rinishida ko'rsatiladi; kalitning o'zi hech qachon chiqarilmaydi.
