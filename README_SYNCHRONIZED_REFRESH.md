# Synchronized Refresh

All dashboard modules now share one 15-second refresh cycle. The previous independent
12s / 15s / 30s timers were removed so Trend Line, Fibonacci, signals, MT5 status,
AI provider status and other visible modules no longer refresh on unrelated cadences.

A refresh cycle will not overlap another cycle. The current market snapshot is
refreshed first, then visible modules are refreshed as one batch. A lightweight
3-second quote heartbeat remains price-only and does not trigger analysis refreshes.
