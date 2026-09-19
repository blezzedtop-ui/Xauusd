from pathlib import Path
import re

p=Path('mt5/SignalX_MultiBroker_Gateway_EA.mq5')
s=p.read_text()

def count(pattern): return len(re.findall(pattern,s))

def test_missing_definitions_fixed():
    assert count(r'input string XAUTradeSymbol') == 1
    assert count(r'input int DuplicateCooldownSeconds') == 1
    assert count(r'double NormalizePrice\(') == 1

def test_multibroker_xau_guard():
    assert 'return (Canonical(symbol)=="XAU/USD");' in s
    assert 'return FindBrokerSymbol("XAU/USD");' in s

def test_valid_levels_is_execution_gate():
    assert 'if(!ValidSignalLevels(symbol,direction,sl,tp))' in s
    assert s.index('if(!ValidSignalLevels(symbol,direction,sl,tp))') < s.index('trade.Buy(')
    assert s.index('if(!ValidSignalLevels(symbol,direction,sl,tp))') < s.index('trade.Sell(')

def test_duplicate_guard():
    assert 'if(!GuardAllows(order_id))' in s
    assert 'if(sent) MarkOrderGuard(order_id);' in s
