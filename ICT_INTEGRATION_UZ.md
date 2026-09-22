# SignalX ICT-only integratsiyasi

- 9 ta bo‘lim: oldingi sakkiz bo‘lim va ICT Analysis. Boshqa strategiyalar 410, generic record-module yopiq.
- Signal faqat yopilgan H4/H1/M30/M15/M5 shamlaridan aniqlanadi; M5 sweep → MSS+displacement → FVG retest. Live Entry og‘ishi, strukturaviy SL va tarixiy TP likvidligi uchun RR >= 1.40.
- AI tasdig‘i 85+, agreement 70+, validation true. AI xatosi yoki rule-based fallback bo‘lsa AutoTrade va yangi History yozuvi yo‘q (UI WAIT).
- Tasdiqlangan ICT signal History'ga yagona candle/source yozuvi orqali saqlanadi; agar admin MT5 AutoTrade ON bo‘lsa mavjud MT5 Bridge va account-scoped gateway'ga yuboriladi. Boshqa bo‘limlar queue'ga kiritilmaydi.
- Startup worker brauzer ochiq bo‘lmaganda ham tekshiradi, bozor yopiq bo‘lsa signal yaratmaydi. Eski History order sifatida replay qilinmaydi.
- MT5_AUTO_TRADING yangi versiyada default OFF: dashboardda admin ON qilganda ishga tushadi. Demo hisobda end-to-end sinang: backend, Market API, AI API, MT5 bridge token, EA symbol mapping, spread/slippage va lotni tekshiring. Railway'da barcha broker narxlarining mosligini ishlab turgan bozor bilan tasdiqlash zarur.
- Eslatma: oldingi main.py ning umumiy kodidagi boshqa strategiya yordamchi funksiyalari qoldirilgan, lekin ularga API yo‘llari yopiq.

- Economic Calendar ichidagi TradingView widget backendda iqtisodiy yangilik eventlarini bermaydi: ushbu versiyada mustaqil HIGH-impact blackout avtomatik tasdiqlanmagan; broker spredi va EA narx og‘ishidan tashqari yangilik riskini o‘zingiz nazorat qiling.

- Eski account-scoped MT5 PENDING/SENT orderlarining manbasi ICT bo‘lmasa, gateway CANCELLED_RETIRED_MODULE qilib EA ga bekor qilish komandasi beradi. Allaqachon bajarilgan real pozitsiyalar avtomatik yopilmaydi.
