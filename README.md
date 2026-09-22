# SignalX — 9 independent strategies (SX9-1)

This is the complete existing FastAPI/Railway website with its frontend, assets,
MT5 EAs and tests. The nine strategy pages now use a new isolated strategy suite.
It is not deployed by downloading this ZIP.

## Sidebar and strategies

| # | Section | Independent entry model |
|---|---|---|
| 3 | ICT AI Pro | M30 bias, M5 liquidity sweep, displacement/MSS, first FVG retest |
| 4 | SNR | Confirmed swing clusters, S/R rejection, opposing-level target check |
| 5 | AI Analysis | Efficiency-ratio regime; trend Donchian breakout or range Bollinger re-entry |
| 6 | Trend | Higher-timeframe alignment, EMA20/50 trend, EMA20 pullback rejection |
| 7 | Trend liniya | Two confirmed swing anchors, intact line, third-touch rejection |
| 8 | Technical Analysis | Bollinger squeeze breakout with RSI and MACD momentum |
| 9 | Classic Trade | Confirmed double top/bottom, neckline break and later retest |
| 10 | OB Trade | Structure-breaking displacement, fresh opposing-candle OB, first retest |
| 11 | Fibonacci Trade | Confirmed impulse, 50–61.8% retracement, rejection and HTF alignment |

Full sidebar: Dashboard, Chart, ICT AI Pro, SNR, AI Analysis, Trend, Trend liniya,
Technical Analysis, Classic Trade, OB Trade, Fibonacci Trade, MT5, History.
ICT Signals and the old consensus scanner are retired. Strategies do not vote
on, merge with, or change each other's decisions.

## RR settings

Each section has its own server-persisted Target RR and timeframe configuration.
Admins can enter **any finite RR >= 1**, e.g. 1, 1.05, 1.4, 1.5, 2, 2.7 or 10.
Default target RR is 2. There is no arbitrary upper cap. A structural obstacle,
nonpositive target, invalid geometry or excessive risk can still make the
strategy return WAIT; a large requested RR cannot force a valid setup.

ICT uses M5 with M30 context. Other sections support M5, M15, M30, H1 and H4.
M1 remains chart-only. Changes apply to the next newly evaluated candle; an
already evaluated signal and its History levels are never rewritten.

AutoTrade accepts actual reward/risk >= 1, recomputed from Entry, SL and TP.
Old AUTOTRADE_MIN_RR=1.40 / AI_PREVALIDATION_MIN_RR values no longer override this
floor. One TP is used for both History and execution. The broker EA recomputes
RR after tick normalization and using bid/ask plus the configured deviation
allowance. A nominal 1:1 setup may therefore be rejected after spread or adverse
price movement. No post-fill RR guarantee is possible under broker slippage.

## Signal and History contract

- Only TradingView, RealMarketAPI or Twelve Data live-provider snapshots enter
  the suite. Yahoo/demo fallbacks, malformed OHLC, recent data gaps and stale
  bars return WAIT. Freshness is based on provider bar timestamps, not proof of
  zero quote latency.
- Only completed entry and higher-timeframe candles determine the setup.
- Every directional candidate gets its own real AI provider veto. Matching
  direction, boolean validation=true, confidence >= 85, agreement >= 70 and no
  blocking risk flags are mandatory. No AI key, errors or fallback means WAIT.
  These model scores are not measured win probabilities.
- One durable evaluation per module/symbol/timeframe/closed candle, including
  failed AI decisions. Concurrent refreshes and process restarts do not cause
  another AI validation of the same event.
- The server scanner runs without an open browser and writes separate History
  rows for each registered user and module, even while AutoTrade is OFF.
- History has source filters and per-module statistics. SX9 signal IDs isolate
  current results from old algorithms. Older rows are preserved in the database
  but excluded from the new suite's History/statistics. Upgrades do not clear it.
- Browser-posted prices, RR, direction and AI claims cannot create an order:
  the server recalculates the canonical module result.
- The durable outbox keeps gateway delivery deduplicated across restarts.
  Legacy delivery uses an atomic at-most-once claim; ambiguous lost responses
  are not blindly replayed. Such cases require terminal reconciliation.
- Gateway execution replies are retained under the correct user's module row
  and account ID. Signal-level chart outcomes and broker account execution
  reports are distinct; chart-derived price differences are not broker P&L.
- A signal may remain in History while execution is disabled, expired, rejected
  by spread/RR checks, or blocked by account limits.

## Railway setup

Required variables: ADMIN_LOGIN, ADMIN_PASSWORD (12+ characters), SECRET_KEY
(stable random value), DATABASE_URL (persistent PostgreSQL recommended).
See .env.example. Preserve the existing database and take a backup before
replacing application files. Deploy using the supplied Dockerfile/railway.json
and the existing main:app entry point. Database additions are additive tables.

Configure valid market/AI provider keys and model IDs for your own accounts.
The new suite never fabricates market data or substitutes rule-only AI approval.
Market Gate blocks new evaluation/AI/orders during closed sessions.

## MT5 setup

Use exactly one transport:

1. **Existing bridge (default)**: MT5_EXECUTION_TRANSPORT=legacy.
   Compile and attach mt5/SignalX_XAUUSD_EA.mq5 in MetaEditor. Set ApiBase and
   BridgeToken to your existing server and MT5_BRIDGE_TOKEN.
2. **Account gateway**: MT5_EXECUTION_TRANSPORT=gateway.
   Compile and attach mt5/SignalX_MultiBroker_Gateway_EA.mq5. Use the site's
   pairing flow and enable AutoTrade for the chosen account.

Set MT5_AUTO_TRADING=true and AUTO_ENTRY_ENABLED=true only when ready; the
distributed environment defaults to AutoTrade OFF. Enable terminal Algo Trading
and allow WebRequest for your API domain. Install the updated EA, not an old
compiled EX5: both EAs now allow exactly the nine active sources and check RR >= 1.
The aggregate EA default is at most 3 open SignalX positions per symbol; lot,
spread and deviation controls remain configurable. The gateway honors each
account's configured lot. Account authorization and broker margin/stops checks
remain in place.

Do not run both EAs for the same strategy/account. The server enables only the
selected transport, avoiding duplicate delivery through two integrations.

## Verification and limitations

Current release checks are in STRATEGY_SUITE_RELEASE.md. Run:

```bash
python -m pip install -r requirements.txt pytest
python -m pytest tests -q
node --check app.js
node --check assets/strategy-suite.js
# Install jsdom in a temporary development directory, then:
NODE_PATH=/path/to/node_modules node tests/test_strategy_ui.cjs
```

The Python tests create a temporary database, synthetic market fixtures and mock
AI/MT5 responses. They neither trade nor measure profitability. DOM tests verify
all navigation links and the nine separate panels and RR forms.

No historical performance backtest, real provider acceptance test, MetaEditor
compilation or live/demo terminal fill test is claimed for this release. Run a
cost-aware historical backtest and demo forward test before real account use.
There is no substantiated “world's strongest” or guaranteed-profit claim.

Historical 2026-09-19 audit files in the archive describe older builds; they are
not verification of SX9-1.

## Reference concepts

The rule sets above are explicit implementation choices, not endorsed systems.
Background references:
- CME technical analysis: https://www.cmegroup.com/education/courses/technical-analysis
- CME risk/reward examples: https://www.cmegroup.com/education/courses/trade-and-risk-management/the-2-percent-rule
- MQL5 order result checks: https://www.mql5.com/en/docs/trading/ordersend

No credentials or production database is included in this distribution.
