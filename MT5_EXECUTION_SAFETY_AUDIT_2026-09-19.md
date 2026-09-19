# SignalX MT5 Execution Safety Audit

Implemented on both MQ5 EAs:

- StopLevel + FreezeLevel validation before every order attempt (existing guard retained and refreshed before send).
- Free-margin check using `OrderCalcMargin()` before send and before retry.
- Reconnect/duplicate protection via persistent GlobalVariable order guard (existing guard retained).
- Retry protection: MultiBroker EA now retries only transient broker retcodes and caps attempts at 3; XAU EA already used transient-only retry.
- Optional per-symbol SignalX position cap via `MaxOpenPositionsPerSymbol` (0 = unlimited; counts only SignalX magic positions).
- Existing spread, volume, symbol, account/terminal/EA permission, market-session and invalid-level guards retained.

Validation performed in this environment:

- Python regression suite: 14 passed.
- Static MT5 audit: 100 runs / 3,400 checks / 0 failures.
- MQ5 delimiter/string/comment scan: both EAs PASS; no unmatched `()`, `[]`, `{}` and no non-ASCII source characters detected.

Important: MetaEditor/MQL5 compiler is not available in this environment, so this is not a claim of 100 successful MetaEditor compilations. Final compile should be run in MetaEditor on the Windows VPS.
