"""SignalX canonical contract regression checks (generated 2026-09-19).
Run with: python -m pytest tests/test_signal_contract_audit.py
"""
def canonical_signal_ok(payload):
    signal=str(payload.get("signal","WAIT")).upper()
    assert signal in {"BUY","SELL","WAIT"}
    if signal=="WAIT":
        assert payload.get("entry") is None
        assert payload.get("stop_loss") is None
        assert payload.get("take_profit",[])==[]
    return True

def ai_gate_ok(ai, direction, rr):
    return (
        ai.get("mode") not in {"fallback","rule_based","unavailable","deferred","skipped"}
        and str(ai.get("signal","WAIT")).upper()==direction
        and int(ai.get("confidence",0))>=85
        and int(ai.get("agreement",0))>=70
        and float(rr or 0)>=1.50
    )
