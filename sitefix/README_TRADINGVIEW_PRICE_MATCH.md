# TradingView price match fix

The dashboard price next to XAU/USD is now a canonical TradingView/OANDA quote.
It does not fall back to RealMarketAPI/Twelve Data, because doing so can show a
second XAUUSD feed that differs from the embedded TradingView chart.

TradingView scanner order: CFD -> Forex compatibility fallback.
If TradingView quote is temporarily unavailable, the previous visible price is
kept instead of replacing it with a different provider.

The Book/OpenAI candle history remains unchanged. The dashboard display price is
separated from provider candle history so the two feeds are not mislabeled as one.
