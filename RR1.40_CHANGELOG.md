# SignalX — RR 1.40 update

Minimum signal/execution RR is now 1.40 across active strategy engines.

Updated hard RR gates:
- Technical/Advanced/AI Signals: 1.40
- MSAI/SNR: 1.40
- SMC: 1.40
- Algo/SMC: 1.40
- Fibonacci: 1.40 label/gate
- Trend Channel / Strategic Pro: 1.40 target floor
- ICT: 1.40 target floor
- AutoTrade / MT5 queue: 1.40

Also included:
- ICT Signals restored in sidebar
- AI Signals source blocker fixed in both bundled MT5 EAs

Verification:
- Python syntax compilation: PASS
- Project tests: 21 passed
- No remaining RR hard-gate comparisons at 1.50 found in active Python/JS/HTML source
- No remaining risk*1.5 signal target defaults found in active Python source

Note: unrelated 1.5/1.55 constants used for ATR/volume/pattern calculations were not changed because they are not RR thresholds.
