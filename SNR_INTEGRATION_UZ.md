# SignalX — SNR Analysis (Support & Resistance)

11 bo‘lim: avvalgi 8 ta bo‘lim + ICT Analysis + Fibonacci Analysis + yangi SNR Analysis.

## Signal oqimi
- 4h va 1h trend; 1h’da kamida 2 ta mustaqil, tasdiqlangan pivotdan SNR narx zonalari.
- M15 kontekst va yopilgan M5 shamda Support Bounce / Resistance Rejection yoki Breakout + Retest.
- SL zonadan tashqarida; TP keyingi haqiqiy qarama-qarshi H1 zonasida. RR kamida 1.40; target matematik RR yaratish uchun soxtalashtirilmaydi.
- AI SNR tahlili: STRONG zone_quality, trend_alignment, candle_confirmed, >=85 heuristic confidence, >=70 agreement. Barcha API xatolarida WAIT.
- Signal History: source=SNR Analysis va candle_time orqali dedupe. Eski source=SNR / MSAI/SNR/retired modules qayta faol emas.
- MT5: core queue, account gateway va EA faqat ICT Signals, Fibonacci, SNR Analysis manbalarini qabul qiladi. Auto Trading admin tomonidan ON qilinmaguncha OFF.
- Shu kodni broker, MT5 terminali va haqiqiy AI kredensiallari bilan demo hisobda alohida sinang. Sun’iy test brokerda bajarilgan real order emas.
