# Existing saytga birlashtirish

Railway'dagi XAUUSD servis alohida backend bo'lib qoladi. Boshqa saytga Python/Node o'rnatish shart emas.

## 1) Tayyor widget

Saytda signal chiqadigan joyga:

```html
<div id="xauusd-ai-widget"></div>
<script
  src="https://SIZNING-RAILWAY-DOMENINGIZ/xauusd-ai-widget.js"
  data-api="https://SIZNING-RAILWAY-DOMENINGIZ/api/market"
  data-ai-api="https://SIZNING-RAILWAY-DOMENINGIZ/api/ai-analysis"
  data-target="xauusd-ai-widget"
  data-refresh="30000">
</script>
```

## 2) O'z dizayningizga ulash

Frontend quyidagi JSON endpointlarni ishlatadi:

`GET /api/market`
`GET /api/ai-analysis`
`GET /api/health`

API keylar hech qachon browserga berilmaydi. Ular Railway Variables'da qoladi.

## 3) Arxitektura

Boshqa sayt
→ Railway API
→ real XAU/USD market data
→ 10 ta strategiya
→ OpenAI
→ JSON
→ boshqa saytning chart/UI

Agar boshqa saytda allaqachon TradingView Lightweight Charts yoki boshqa chart bo'lsa, `/api/market` candle ma'lumotlarini o'sha chartga va `/api/ai-analysis` natijalarini signal paneliga ulash mumkin.

## 4) To'g'ridan-to'g'ri kodga qo'shish

Agar siz menga boshqa saytning ZIP faylini yuborsangiz, shu widgetni emas, uning ichiga bevosita:
- XAUUSD M30 chart
- 10 strategiya
- OpenAI signal
- Entry/SL/TP
- support/resistance zonalari
ni mavjud dizaynni buzmasdan birlashtirish mumkin.
