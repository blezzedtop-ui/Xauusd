# SignalX — Order Block Analysis

12 bo‘lim: avvalgi 8 ta + ICT + Fibonacci + SNR Analysis + Order Block Analysis.

## Algoritm va oqim
- H4/H1 trendni aniqlash; M15 da 3+3 yopilgan shamda tasdiqlangan swing, BOS va bitta yopilgan 1.5x ATR(14) impuls sham.
- Impulsdan avvalgi 5 sham ichidagi oxirgi qarama-qarshi M15 sham zona; tekshirilmagan/fresh zona. Ilk yopilgan M5 retest + rejection kutiladi.
- SL OB hududidan va M5 wick’dan tashqarida. TP haqiqiy mavjud H1 ekstremumida, sun’iy 1.40 TP yaratilmaydi. RR kamida 1.40.
- AI tekshiruvchi: STRONG zona, H4/H1 bias, BOS, displacement, retest, confidence >=85 va agreement >=70. AI narxlarni almashtira olmaydi. AI yo‘q -> WAIT.
- Signal History: `source=Order Block Analysis`, yopilgan `candle_time` bo‘yicha alohida deduplikatsiya. `WAIT`/ishlamagan OB savdo statistikasi emas.
- MT5: core queue, account gateway va ikkita EA yangi manbaga ruxsat beradi. Oldingi `Order Block` manbasi ruxsatsiz qoladi.
- Auto Trading odatda OFF. Admin tomonidan yoqilganda demo hisobda risk, spread va deviation tekshirish zarur.

Sinovlar sintetik OHLC uchun; brokerda orderning bajarilishi va strategiyaning foydaliligi kafolatlanmaydi.
