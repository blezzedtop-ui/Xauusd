# SignalX — Fibonacci Analysis integratsiyasi

- 10 bo‘lim: oldingi 8 bo‘lim, ICT Analysis, Fibonacci Analysis. O‘chirilgan boshqa strategiya endpointlari 410.
- Fib M15 yopilgan shamlar, H4/H1 trend, tasdiqlangan swing, 0.500–0.618 qaytish zonasi, yopilgan M15 sham tasdig‘i, 1.272/1.618 kengaytma darajalari. RR >= 1.40, SL invalidatsiya ortida, narx og‘ishi va eskirish nazorati.
- AI `validation=true`, direction mos, confidence >=85, agreement >=70 bo‘lmasa yangi Signal History/MT5 order YO‘Q. Fib va ICT History alohida. Takroriy candle/source yozuvi rad etiladi.
- Faqat `ICT Signals` va `Fibonacci` MT5 navbatiga va ikki bridge turiga kiradi; eski manbalar bloklangan. Startup worker ikkisini skanerlaydi. Avto savdo oldindan OFF, admin yoqadi.
- Testlar synthetic signal oqimini tekshiradi. Haqiqiy brokerda order bajarilgani va foyda darajasi kafolatlanmaydi. Avval MT5 demo, bid/ask, spread, symbol suffix, lot/margin, API va EA hisobotini tekshiring.
