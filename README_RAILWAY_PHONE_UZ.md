# XAUUSD V36 — Railway Phone-Only Deploy

Bu paket FastAPI + frontendni bitta Railway service sifatida ishga tushirish uchun tayyor.
Kompyuterda Python yoki CMD ishlatish kerak emas: deploy tugagach sayt Railway HTTPS domeni orqali telefondan ochiladi.

## Railway'da 3 qadam

1. Railway'da **New Project** yarating va GitHub repository orqali shu loyiha papkasini deploy qiling.
2. Project ichida **PostgreSQL** qo'shing. PostgreSQL service'dan `DATABASE_URL` ni app service'ga reference variable sifatida ulang.
3. App service -> **Settings -> Networking -> Generate Domain** bosing. Berilgan `https://...up.railway.app` linkni telefondan oching.

## Muhim environment variables

App service -> Variables:

- `DATABASE_URL` = PostgreSQL service'dagi `DATABASE_URL` reference
- `SECRET_KEY` = uzun tasodifiy maxfiy qiymat
- `MARKET_PROVIDER=auto`
- `ALLOW_DEMO=false`
- `APP_BASE_URL=https://SIZNING-RAILWAY-DOMENINGIZ`

Agar RealMarketAPI kaliti bo'lsa:
- `REALMARKET_API_KEY=...`
- `REALMARKET_API_BASE=https://api.realmarketapi.com`

Agar OpenAI ishlatilsa:
- `OPENAI_API_KEY=...`
- `OPENAI_MODEL=gpt-5`

Calendar kerak bo'lsa:
- `FINNHUB_API_KEY=...`

## Eslatma

`index.html` FastAPI tomonidan `/` route orqali beriladi. Shu sababli frontend va backend bitta domen ostida ishlaydi va `config.js`ga Railway URL yozish shart emas.

PostgreSQL production uchun tavsiya qilinadi; Railway PostgreSQL `DATABASE_URL` orqali ulanadi. SQLite Railway'da doimiy login/history saqlash uchun tavsiya etilmaydi.


## V7 fixes
- Multi-timeframe analysis no longer fails when one RealMarketAPI timeframe is unavailable.
- Analysis endpoint returns visible structured errors instead of blank Signal/Pivot fields.
- Pivot has an M5 fallback.
