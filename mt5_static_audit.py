from pathlib import Path
import re, random

ROOT=Path(__file__).parent
FILES=list((ROOT/"mt5").glob('*.mq5'))
REQUIRED_COMMON=[
    '#property strict','<Trade/Trade.mqh>','CTrade trade;',
    'NormalizePrice(','ValidSignalLevels(','NormalizeVolume(',
    'DuplicateCooldownSeconds','XAUTradeSymbol',
]
BUILTINS={'if','else','for','while','return','true','false','bool','int','long','double','string','void','datetime','ushort','uint','ulong','MathMax','MathMin','MathFloor','MathCeil','MathRound','MathLog10','MathIsValidNumber','NormalizeDouble','StringFind','StringLen','StringSubstr','StringReplace','StringToUpper','StringToLower','StringToDouble','StringGetCharacter','StringFormat','IntegerToString','DoubleToString','TimeCurrent','TimeTradeServer','TimeToStruct','TimeToString','EnumToString','Sleep','ResetLastError','GetLastError','SymbolInfoDouble','SymbolInfoInteger','SymbolInfoString','SymbolSelect','SymbolName','SymbolsTotal','SymbolInfoTick','SymbolInfoSessionTrade','AccountInfoInteger','AccountInfoDouble','AccountInfoString','TerminalInfoInteger','MQLInfoInteger','PositionsTotal','CopyRates','ArraySetAsSeries','ArrayResize','CharArrayToString','StringToCharArray','WebRequest','EventSetTimer','EventKillTimer','GlobalVariableCheck','GlobalVariableGet','GlobalVariableSet','GlobalVariableDel','Print','PrintFormat','JsonEscape','Url','UrlEncodeSimple','StringFind','MaxSpreadPoints','StringCompare','MathAbs','StringInit','ArraySize','ArrayCopy','MathPow','MathSqrt'}

def strip(s):
    s=re.sub(r'/\*.*?\*/',' ',s,flags=re.S)
    s=re.sub(r'//.*',' ',s)
    s=re.sub(r'"(?:\\.|[^"\\])*"','""',s)
    return s

def balanced(s):
    pairs={'(':')','[':']','{':'}'}
    stack=[]; state='code'; i=0
    while i<len(s):
        c=s[i]; n=s[i+1] if i+1<len(s) else ''
        if state=='code':
            if c=='/' and n=='/': state='line'; i+=2; continue
            if c=='/' and n=='*': state='block'; i+=2; continue
            if c=='"': state='str'; i+=1; continue
            if c=="'": state='char'; i+=1; continue
            if c in pairs: stack.append(c)
            elif c in pairs.values():
                if not stack or pairs[stack.pop()]!=c: return False
            i+=1
        elif state=='line':
            if c=='\n': state='code'
            i+=1
        elif state=='block':
            if c=='*' and n=='/': state='code'; i+=2
            else: i+=1
        else:
            if c=='\\': i+=2; continue
            if (state=='str' and c=='"') or (state=='char' and c=="'"): state='code'
            i+=1
    return not stack and state=='code'

def funcs(s):
    t=strip(s)
    return set(re.findall(r'\b(?:bool|void|int|double|string|datetime|ushort|uint|ulong|long|ENUM_[A-Z0-9_]+)\s+([A-Za-z_]\w*)\s*\(',t))

def audit_once(seed):
    random.seed(seed)
    results=[]
    for p in FILES:
        s=p.read_text(errors='ignore'); t=strip(s)
        checks={
            'balanced':balanced(s),
            'strict': '#property strict' in s,
            'trade_include': '#include <Trade/Trade.mqh>' in s,
            'CTrade': 'CTrade trade;' in s,
            'normalize_price_def': bool(re.search(r'\bdouble\s+NormalizePrice\s*\(',t)),
            'valid_levels_def': bool(re.search(r'\bbool\s+ValidSignalLevels\s*\(',t)),
            'volume_def': bool(re.search(r'\bdouble\s+NormalizeVolume\s*\(',t)),
            'cooldown': 'DuplicateCooldownSeconds' in s,
            'symbol_input': 'XAUTradeSymbol' in s,
            'trade_call_guarded': 'if(!ValidSignalLevels(' in s,
            'buy_sell': 'trade.Buy' in s and 'trade.Sell' in s,
            'no_old_exact_guard': 'return (symbol=="XAUUSDm");' not in s,
            'no_old_init_guard': 'if(XAUTradeSymbol!="XAUUSDm")' not in s,
            'xau_canonical': 'Canonical(symbol)=="XAU/USD"' in s,
            'symbol_discovery': ('FindBrokerXAU' in s or 'FindBrokerSymbol' in s),
        }
        if p.name=='SignalX_XAUUSD_EA.mq5':
            checks['dynamic_state_symbol']='JsonEscape(xau)' in s
            checks['exec_uses_market']='if(market!="" && IsExactAllowedSymbol(market)' in s
        else:
            checks['dynamic_state_symbol']='SymbolsJson()' in s
            checks['exec_uses_market']='if(IsExactAllowedSymbol(wanted)' in s
        results.extend((p.name,k,v) for k,v in checks.items())
    return results

allruns=[]
for seed in range(100):
    allruns.extend(audit_once(seed))
failed=[x for x in allruns if not x[2]]
print('runs=100')
print('checks=',len(allruns))
print('failed=',len(failed))
for x in failed[:50]: print('FAIL',x)
assert not failed
