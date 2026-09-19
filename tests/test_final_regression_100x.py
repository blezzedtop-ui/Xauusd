
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
MAIN=(ROOT/"main.py").read_text(encoding="utf-8")
APP=(ROOT/"app.js").read_text(encoding="utf-8")
HTML=(ROOT/"index.html").read_text(encoding="utf-8")
EA1=(ROOT/"mt5"/"SignalX_MultiBroker_Gateway_EA.mq5").read_text(encoding="utf-8")
EA2=(ROOT/"mt5"/"SignalX_XAUUSD_EA.mq5").read_text(encoding="utf-8")

def test_pending_types_and_cancel():
    for x in ("BUY_STOP","SELL_STOP","BUY_LIMIT","SELL_LIMIT"):
        assert x in MAIN and x in EA1 and x in EA2
    assert "OrderDelete" in EA1 and "OrderDelete" in EA2
    assert "CANCELLED_SETUP_INVALID" in MAIN
    assert "CANCELLED_SETUP_EXPIRED" in MAIN

def test_history_lifecycle():
    for x in ("PENDING_CREATED","PENDING_TRIGGERED","MARKET_OPENED","TP1_HIT","TP2_HIT","SL_HIT"):
        assert x in MAIN
    assert "execution" in MAIN

def test_ai_gate():
    assert '"minimum_confidence": 85' in MAIN
    assert '"minimum_agreement": 70' in MAIN
    # SMC must not retain the old 75-confidence gate.
    assert "int(ai.get(\"confidence\", 0)) >= 85 and int(ai.get(\"agreement\", 0)) >= 70" in MAIN

def test_safety():
    for x in ("OrderCalcMargin","SYMBOL_TRADE_STOPS_LEVEL","SYMBOL_TRADE_FREEZE_LEVEL","DuplicateCooldownSeconds","MaxOpenPositions"):
        assert x in EA1 and x in EA2

def test_mobile_history_ui():
    assert "sxMobileMenu" in HTML
    assert ".sx-history-filters" in HTML
    assert ".sx-signal-bottom" in HTML
    assert "flex-wrap:wrap" in HTML

def test_status_column_wide():
    assert 'status: Mapped[str] = mapped_column(String(40)' in MAIN
    assert '"status": "VARCHAR(40) DEFAULT \'ACTIVE\'"' in MAIN

def test_balanced_mq5():
    for src in (EA1, EA2):
        for a,b in [("(",")"),("{","}")]:
            assert src.count(a)==src.count(b), (a,b,src.count(a),src.count(b))
