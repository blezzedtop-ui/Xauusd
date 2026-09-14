# Signal History — TP/SL Pips Final Fix

History now calculates pip distances per individual signal and per symbol.
- XAUUSD: 0.01 price unit = 1 pip
- EURUSD and other non-JPY FX: 0.0001 price unit = 1 pip
- TP Pips: distance to the farthest TP target
- TP Total Pips: sum of distances from Entry to every TP target (API field `tp_pips_total`; UI displays this total)
- SL Pips: absolute Entry→SL distance
- Values are calculated from the stored Entry/TP/SL of that individual signal and never aggregated across different signals or symbols.
