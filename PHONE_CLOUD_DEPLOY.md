# Telefon orqali ishlatish

Bu build local CMD/Node gatewayga bog'liq emas. Hostingda ishga tushirilganda frontend shu domenning backend API'siga ulanadi.

## Tavsiya
1. ZIPni GitHub repositoryga joylang.
2. Railway yoki boshqa Python hostingda shu repositorydan deploy qiling.
3. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Health check: `/api/health`
5. `REALMARKET_API_KEY` bo'lmasa, `MARKET_PROVIDER=auto` holatida Yahoo Finance public chart feed fallback ishlatiladi.
6. TradingView widget chart uchun API key talab qilinmaydi.
7. Hosting bergan HTTPS URLni telefonda oching — kompyuter doimiy yoqilib turishi shart emas.

## Muhim
Yahoo Finance fallback — mustaqil public market feed. U TradingView iframe ichidagi candle ma'lumotlarini scraping qilmaydi. Analysis va Signal backenddagi yagona candle feeddan hisoblanadi.
