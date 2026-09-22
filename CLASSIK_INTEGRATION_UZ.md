# SignalX — Classik Analysis (klassik texnik tahlil)

**Interfeys:** mavjud 14 bo‘limga Classik Analysis qo‘shildi; jami 15 bo‘lim. Oldingi `Classic Trade` API (`/api/v1/classic-trade/...`) bloklanganicha qoladi. Yangi modulning aniq manbasi `Classik Analysis`; unga eski moduldan tarixiy orderlar avtomatik ko‘chmaydi.

## Savdo shartlari

Yopilgan H4/H1/M30 shamlar: umumiy trend bir xil. Yopilgan H1 shamlarning 3 ta chap/3 ta o‘ng tasdig‘idan o‘tgan S/R swing darajasi. M15: darajadan yopilgan sham tanasi bilan breakout, keyingi 2–8 sham ichida **birinchi** retest (zona oldin ishlatilmagan va bekor bo‘lmagan). M5: aynan retest davrida bullish/bearish engulfing yoki pin bar yopilishi. Kirish — eskirmagan kuzatilgan joriy narx; Stop Loss — retest invalidatsiya zonasi tashqarisida; TP — H1 tarixida mavjud keyingi qarama-qarshi narx to‘sig‘i. RR ≥ 1.40 va ≤ 6. Ma’lumot yetishmasa, narx og‘ishi katta, trend zid, retest takroriy yoki SL/TP matematik noto‘g‘ri bo‘lsa `WAIT`. Faqat algoritmik qiymatlar yuboriladi, AI yangi Entry/SL/TP yarata olmaydi.

## AI → History → MT5

`GET /api/v1/classik-analysis-live/XAU%2FUSD` — faqat admin preview; History’da hali tasdiqlanmagan nomzod BUY/SELL sifatida chiqmaydi. `POST /api/v1/classik-analysis/process` — admin uchun real tekshiruv. AI `validation=true`, `signal` mos, `confidence ≥ 85`, `agreement ≥ 70`, `mtf_aligned`, `breakout_valid`, `retest_valid`, `candle_confirmed` true, risk flag yo‘q bo‘lsa va server geometriyasi qayta tekshirsa, `source=Classik Analysis`, `module_id=classic_analysis_v2` bilan Signal History’ga yozadi. Bir xil M5 yopilgan sham va manba takroriy saqlanmaydi. Auto Trading ON bo‘lsa MT5 queue va gateway’ga uzatiladi; EA bozor narxi, spread, broker symbol, margin, stop-level va deviationni ijro paytida qayta tekshiradi. Bir xil Entry, SL, TP boshqa strategiyada navbatga qo‘shilgan bo‘lsa, yangi order bloklanadi, lekin History’lar alohida.

`POST /api/v1/signals/auto-record` umumiy worker ham Classik bilan birga 7 ta aktiv strategiyani tekshiradi. Legacy modullar yopiq, shu jumladan `Classic Trade`. Auto Trading default OFF. AI 401/402/429, timeout, fallbacks, noto‘g‘ri javob yoki 85 dan past bahoda yangi savdo ochilmaydi. Avval Railway deploy, MT5 EA qayta kompilyatsiya va demo hisobda end-to-end sinov zarur.

## Tekshiruv chegarasi

Python/JS sintaksisi, sintetik BUY/SELL, WAIT shartlari, lokal SQLite History, AI stub, duplicate va MT5 queue filtr sinovlari brokerda amalda order bajarilganini yoki strategiya win rate’ini isbotlamaydi. AI confidence — statistik yutish ehtimoli emas.
