# SignalX — Trendline Analysis

13 bo‘lim: avvalgi 8 ta + ICT + Fibonacci + SNR Analysis + Order Block Analysis + Trendline Analysis.

## Mustaqil algoritm
- M5 3+3 yopilgan sham bilan tasdiqlangan ikki swing nuqtasidan o‘suvchi/pasayuvchi trend chizig‘i.
- M5 da uchinchi tegish va rejection yoki yopilgan body bilan breakout + birinchi retest. H4/H1 qarama-qarshi bo‘lmasin, M30 yo‘nalishi mos.
- Real narxdan Entry, trendline/swing ortiga SL, tarixiy H1 ekstremumidan TP; RR ≥ 1.40, past/eskirgan/nomos ma’lumotda WAIT.
- AI validator mustaqil tasdiq: confidence ≥85, agreement ≥70, MTF + candle + trendline + third-touch/retest tasdiqlangan. AI ishlamasa WAIT.
- History: `source=Trendline Analysis`, yopilgan candle_time asosida dublikatni bloklash. Qo‘lda ko‘rish API BUY/SELL’ni AI tasdiqsiz ko‘rsatmaydi.
- MT5: faol manba whitelist'iga faqat yangi `Trendline Analysis` qo‘shilgan. Eski Auto Trend Line va Trend Channel ruxsat olmagan.
- Auto Trading avvalgi kabi OFF holatda. Dastlab demo hisob, spread, lot, narx og‘ishi va umumiy portfel riski tekshiriladi.

Trendline va Fibonacci signallari alohida history manbasiga ega. Ular bir vaqtda kelsa, bitta setupga tegishli dublikatlar uchun hisob darajasidagi risk/pozitsiya nazorati kerak. Mahalliy test real broker ijrosini tasdiqlamaydi.

## Fibonacci bilan takroriy orderdan himoya
MT5 asosiy navbatida bir xil yo‘nalish va deyarli bir xil Entry/SL/TP (tolerans max(0.15, entry*0.00003)) bilan kelgan Fibonacci va Trendline Analysis signallari uchun ikkinchi matching order bloklanadi. Ikki strategiya History'ga alohida tahlil sifatida yozilishi mumkin. Turli Entry/SL/TP bilan kelgan orderlar mustaqil setup deb hisoblanadi; hisob darajasidagi umumiy xavfni alohida nazorat qiling.
