# SignalX — SNR mahalliy tekshiruv natijalari

- BUY: confirmed H1 support + M5 closed rejection, real opposing resistance TP, RR >= 1.40 — PASS.
- SELL: mirrored H1 resistance + M5 closed rejection, real opposing support TP, RR >= 1.40 — PASS.
- WAIT: M5 candle tasdig‘i yo‘q, live price yo‘q, narx og‘ishi katta, eskirgan M5 sham va yetarli sham yo‘q — PASS.
- AI approval, zone quality, dedupe, History write, AutoTrade OFF, MT5 queue ON, retired source filtering, RR geometry — PASS.
- Admin-only SNR preview, eski Classic Trade 410, ICT/Fibonacci worker bilan birga ishlashi, 11 sidebar bo‘lim — PASS.
- Avvalgi ICT va Fibonacci integratsiya testlari — PASS; eski ICT testning doimiy SQLite ma’lumotlari takror yozuvga olib kelgani uchun fresh test SQLite bilan qayta bajarildi.
- JavaScript `node --check` va Python `py_compile` — PASS.

Cheklovlar: MT5 EA MetaEditor’da kompilyatsiya qilinmadi; Railway, real API key, real broker bid/ask, order fill va strategiya samaradorligi tekshirilmagan. Testlar sun’iy shamlar va mock AI/MT5 navbati orqali bajarilgan. Default AutoTrade OFF; dastlab demo hisobda sinov shart.
