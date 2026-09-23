# SignalX Professional Signal History V2

Rebuilds Signal History as a trading journal/audit layer. Existing SignalX signal modules and AutoTrade execution logic remain separate. The v2 history API provides date, symbol, direction, result and module filtering plus KPI/module/day statistics. Signal-time payloads are frozen in `history_snapshot`. TP1 is intermediate; TP2/SL are final outcomes for win rate.

Deployment is intentionally not performed.
