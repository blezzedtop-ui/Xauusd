# SX9-1 release — 2026-09-22

This release replaces the old UI-only restoration and dormant ICT-only worker.
Nine independent closed-candle rule sets use one shared, strict signal contract.
History is durable and source-separated; a server worker runs without the page
being open. Arbitrary finite target RR >= 1 is configurable separately per module.

Changes include:

- Dedicated ICT, SNR, regime/AI, trend, trendline, technical, classic, OB and
  Fibonacci strategies; separate AI validation and source identity.
- Additive strategy settings, event and outbox tables. No History purge on boot.
- Server-authoritative module recording, immutable signal snapshots, database
  uniqueness and per-candle AI deduplication. Old signal API routes are retired.
- Exactly nine sources allowed in the backend and both EAs. Queue and EA
  calculate RR from the levels actually used, not a client-supplied number.
- Legacy/gateway transport selection, durable/atomic legacy claims, stable IDs,
  gateway per-account journal references and execution reports.
- Gateway numeric order ID parsing, XAU/USD canonical symbol handling, broker
  result-code checks and no blind timeout retry. Successful EA IDs are retained.
- Nine separate responsive panels, live-feed candle plots, RR forms and exact
  History filters. A dashboard summary replaces the retired AI Signals card.
- Current-strategy History excludes legacy rows while retaining them in storage.
  Candle ranges before signal creation cannot inflate its result statistics.

Verification performed locally with no real orders/provider calls:

- Python regression suite: 41 tests plus 26 parameterized subtests passed.
- Engine fixtures: all nine modules have independently verified BUY and SELL
  paths, invalid-data WAIT paths, and RR/structural-target checks.
- Backend fixtures: per-module History and stats, repeat/concurrent requests,
  arbitrary RR validation, AI/data failure, forged client prices, outbox restart,
  source/timeframe identity, AutoTrade OFF, gateway ownership/claims/reports,
  old-history retention and pre-signal price-action exclusion.
- DOM integration: 13 navigation items; all nine module panels, real-data plot
  rendering, distinct History IDs, fractional RR saving and source filters.
- Python compilation and JavaScript syntax checks passed.

These checks validate software behavior, not trading returns. EA changes were
statically inspected; MetaEditor compilation and a connected demo-terminal fill
test remain deployment checks. No live deployment, backtest win rate, profitability
or “strongest strategy” claim is made. See README.md before installation.
