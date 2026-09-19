# Legacy SNR removal — 2026-09-19

The legacy standalone/clustered SNR signal source has been removed from the active SignalX pipeline.

Active SNR logic is only the Malaysian SNR implementation inside MSAI Strategy v1.0.
Legacy SNR sources are blocked from auto-trade and module-history recording, and excluded from history reads.
Classic Trade no longer uses SNR. Generic Signal Engine no longer exposes an SNR component.
