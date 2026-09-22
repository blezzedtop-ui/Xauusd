# SignalX — Texnik Analysis integratsiyasi

**Faol sidebar:** avvalgi 13 bo‘lim va Texnik Analysis = 14 bo‘lim. Eski `Technical Analysis` endpointi qayta ochilmaydi.

## Algoritm

Yopilgan H1 (kamida 215 sham): EMA50 va EMA200 orqali trend. Yopilgan M15: faqat 2+2 tasdiqlangan swing support/resistance pivoti. M5: yopilgan bullish/bearish engulfing yoki pin bar, EMA50 va RSI14 mosligi. Joriy narx yopilgan M5 narxidan ortiqcha uzoqlashmagan bo‘lishi kerak. SL tasdiqlangan zona tashqarisida, TP esa **keyingi kuzatilgan H1 narx to‘sig‘i** bo‘ladi; RR kamida 1.40, ko‘pi 6. Har qanday ma’lumot/indikator/tasdiq yetishmasa WAIT. Sun’iy TP bilan RR to‘ldirilmaydi.

## AI + History + MT5

`/api/v1/technical-live/XAU%2FUSD` — administrator uchun ko‘rish; tasdiqlanmagan nomzod BUY/SELL ko‘rinishida chiqarilmaydi. `/api/v1/technical/process` — admin tomonidan tekshirish, qat’iy AI tasdiq, Risk/geometry validation, `source=Texnik Analysis` bilan History yozish va faqat Auto Trading ON bo‘lsa MT5 navbatiga qo‘shish. Umumiy `/api/v1/signals/auto-record` worker ham Texnik’ni tekshiradi. Har bir yopilgan M5 sham va source bo‘yicha dublikat History rad etiladi; bir xil Entry/SL/TP qayta navbatga qo‘shilmaydi.

AI ishlamasa, `mode=fallback/rule_based/unavailable` yoki tasdiq yetishmasa, order bloklanadi. So‘nggi bozor narxi, spread, margin, broker symbol mosligi va price deviation uchun MT5 EA ning ijro paytidagi himoyasi saqlanadi. Auto Trading default OFF. Railway ga deploy va MetaEditor’da EA kompilyatsiyasidan so‘ng avval demo hisobda haqiqiy broker ijrosini tekshiring.

**Chegara:** lokal sintetik va integratsion testlar haqiqiy bozor, haqiqiy LLM, haqiqiy EA kompilyatsiyasi yoki real broker orderi bajarilishini isbotlamaydi. Strategiyaning natijadorligi kafolatlanmaydi.
