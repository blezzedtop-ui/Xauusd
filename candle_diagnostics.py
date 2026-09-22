"""Non-trading diagnostics for the seven independent strategy engines."""

def attach_candle_diagnostics(result, frames, requirements):
    counts = {tf: len(frames.get(tf) or []) for tf, _ in requirements}
    required = dict(requirements)
    result["candle_diagnostics"] = {
        "available_closed": counts,
        "required_closed": required,
        "missing": {tf: required[tf] - counts[tf] for tf in required if counts[tf] < required[tf]},
    }
    return result
