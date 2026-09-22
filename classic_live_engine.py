"""Independent, closed-candle Classic Breakout + First Retest scanner for XAUUSD.

No I/O, database, AI, order placement or invented targets. The old Classic Trade
engine is deliberately not imported: that source remains retired.
"""
from __future__ import annotations
import math
import time
from ict_engine import _atr, _bias, TF_SECONDS

MIN_RR=1.40


def _confirmed_pivots(bars, field, radius=3):
    points=[]
    for i in range(radius,len(bars)-radius):
        val=bars[i][field]
        around=[b[field] for b in bars[i-radius:i+radius+1]]
        if (val==(max(around) if field=='high' else min(around))) and around.count(val)==1:
            points.append((i,val))
    return points


def analyze_classic_live(frames, *, live_price=None, now=None, min_rr=MIN_RR):
    now=time.time() if now is None else float(now)
    m5=frames.get('5min') or []
    out={'module_id':'classic_analysis_v2','source':'Classik Analysis','signal':'WAIT','state':'WAIT',
         'reason':'INSUFFICIENT_CLOSED_CANDLES','confidence':0,'entry':None,'stop_loss':None,
         'take_profit':[],'risk_reward':None,'candle_time':str(m5[-1]['time']) if m5 else '',
         'bias':'NEUTRAL','breakout':None,'retest':None,'candle_pattern':'NONE','checks':{},
         'model':'Closed H4/H1/M30 trend + confirmed H1 S/R + M15 breakout and first retest + closed M5 confirmation'}
    def wait(reason):
        out['reason']=reason
        return out
    needs=(('4h',55),('1h',75),('30min',65),('15min',85),('5min',85))
    if any(len(frames.get(tf) or [])<minimum for tf,minimum in needs):return wait('INSUFFICIENT_CLOSED_CANDLES')
    for tf,_ in needs:
        seq=frames[tf]
        if any(seq[i]['time']<=seq[i-1]['time'] for i in range(1,len(seq))):return wait('NON_MONOTONIC_CANDLES')
        if seq[-1]['time']+TF_SECONDS[tf]>now:return wait('UNFINISHED_CANDLE')
        if now-(seq[-1]['time']+TF_SECONDS[tf])>(360 if tf=='5min' else 2.5*TF_SECONDS[tf]):
            return wait('STALE_'+tf.upper()+'_CANDLE')
    try:entry=float(live_price)
    except (TypeError,ValueError,OverflowError):return wait('LIVE_PRICE_UNAVAILABLE')
    if not math.isfinite(entry) or entry<=0:return wait('LIVE_PRICE_UNAVAILABLE')
    h4,h1,m30,m15=(frames[tf] for tf in ('4h','1h','30min','15min'))
    b4,b1,b30=(_bias(v) for v in (h4,h1,m30))
    out['bias']=b1
    if b1=='NEUTRAL' or b4!=b1 or b30!=b1:return wait('HTF_TREND_CONFLICT')
    direction='BUY' if b1=='BULLISH' else 'SELL'
    a5,a15=_atr(m5),_atr(m15)
    if not all(math.isfinite(v) and v>0 for v in (a5,a15)):return wait('INVALID_ATR')
    last=m5[-1];prev=m5[-2]
    if abs(entry-last['close'])>max(.30*a5,entry*.00010):return wait('ENTRY_DEVIATION_TOO_LARGE')
    # M5 retest confirmation must not predate the closed M15 retest bar.
    if not (m15[-1]['time']+600 <= last['time'] <= m15[-1]['time']+1200):
        return wait('M5_M15_CONFIRMATION_MISMATCH')
    tol=max(.20*a15,.14*a5,entry*.000025)
    # A level is eligible only when it was a confirmed 3+3 H1 pivot before the
    # M15 breakout (no look-ahead of the later H1 candle).
    cutoff=m15[-9]['time']
    pivots=_confirmed_pivots(h1,'high' if direction=='BUY' else 'low')
    historic=[(i,level) for i,level in pivots if h1[i+3]['time']+3600<=cutoff]
    if not historic:return wait('NO_CONFIRMED_H1_SR_LEVEL')
    candidates=[]
    n=len(m15)-1
    for _,level in historic[-14:]:
        for j in range(max(1,n-8),n-1):
            br=m15[j];before=m15[j-1]
            crossed=(before['close']<=level+tol*.1 and br['open']<=level+tol*.3
                     and br['close']>level+tol and br['close']>br['open']) if direction=='BUY' else (
                     before['close']>=level-tol*.1 and br['open']>=level-tol*.3
                     and br['close']<level-tol and br['close']<br['open'])
            if not crossed or abs(br['close']-br['open'])<.55*a15:continue
            post=m15[j+1:n]
            # Do not accept an earlier test or an invalidated zone.
            if direction=='BUY':
                invalid=any(b['close']<level-tol for b in post)
                used=any(b['low']<=level+tol for b in post)
                retest=m15[-1]['low']<=level+tol and m15[-1]['close']>level+tol*.2
            else:
                invalid=any(b['close']>level+tol for b in post)
                used=any(b['high']>=level-tol for b in post)
                retest=m15[-1]['high']>=level-tol and m15[-1]['close']<level-tol*.2
            if invalid or used or not retest:continue
            candidates.append((j,level,br))
    if not candidates:return wait('WAIT_CONFIRMED_BREAKOUT_FIRST_RETEST')
    # Require price action on the latest closed M5 candle, not an open/current bar.
    bullish=(last['close']>last['open'] and last['close']>prev['close'])
    bearish=(last['close']<last['open'] and last['close']<prev['close'])
    body=max(abs(last['close']-last['open']),.04*a5)
    lower=max(0,min(last['open'],last['close'])-last['low'])
    upper=max(0,last['high']-max(last['open'],last['close']))
    engulf_buy=(prev['close']<prev['open'] and last['open']<=prev['close'] and last['close']>=prev['open'])
    engulf_sell=(prev['close']>prev['open'] and last['open']>=prev['close'] and last['close']<=prev['open'])
    if direction=='BUY':
        pattern='BULLISH_ENGULFING' if bullish and engulf_buy else ('BULLISH_PIN_BAR' if bullish and lower>=1.6*body and upper<=1.2*body else 'NONE')
    else:
        pattern='BEARISH_ENGULFING' if bearish and engulf_sell else ('BEARISH_PIN_BAR' if bearish and upper>=1.6*body and lower<=1.2*body else 'NONE')
    out['candle_pattern']=pattern
    if pattern=='NONE':return wait('M5_CANDLE_NOT_CONFIRMED')
    eligible=[]
    for j,level,br in candidates:
        if direction=='BUY':
            if not (last['low']<=level+tol and last['close']>level+tol*.2):continue
            stop=min(m15[-1]['low'],last['low'],level)-max(.15*a5,entry*.000025)
            targets=sorted({v['high'] for v in h1[-75:] if v['high']>entry+tol})
            tp=targets[0] if targets else None
            risk=entry-stop;reward=(tp-entry) if tp is not None else -1
        else:
            if not (last['high']>=level-tol and last['close']<level-tol*.2):continue
            stop=max(m15[-1]['high'],last['high'],level)+max(.15*a5,entry*.000025)
            targets=sorted({v['low'] for v in h1[-75:] if v['low']<entry-tol},reverse=True)
            tp=targets[0] if targets else None
            risk=stop-entry;reward=(entry-tp) if tp is not None else -1
        if tp is None or risk<=0 or reward<=0:continue
        rr=reward/risk
        if not (max(MIN_RR,float(min_rr))-1e-9<=rr<=6):continue
        if not all(math.isfinite(x) and x>0 for x in (entry,stop,tp)):continue
        if not ((stop<entry<tp) if direction=='BUY' else (tp<entry<stop)):continue
        eligible.append((j,level,br,stop,tp,rr))
    if not eligible:return wait('WAIT_FIRST_RETEST_TARGET_OR_RR')
    # One deterministic setup, latest breakout. Multiple different valid levels
    # on the same candle are ambiguous: do not send conflicting MT5 orders.
    latest=max(x[0] for x in eligible)
    chosen=[x for x in eligible if x[0]==latest]
    if len({round(x[1],4) for x in chosen})!=1:return wait('AMBIGUOUS_BREAKOUT_LEVEL')
    j,level,br,stop,tp,rr=chosen[0]
    out.update(signal=direction,state='READY',reason='H4/H1/M30 aligned; confirmed H1 pivot; closed M15 breakout and first retest; closed M5 candle; observed H1 TP',
               confidence=89 if 'ENGULFING' in pattern else 86,
               entry=round(entry,5),stop_loss=round(stop,5),take_profit=[round(tp,5)],
               risk_reward=round(rr,4),
               breakout={'level':round(level,5),'time':br['time'],'direction':direction,'confirmed':True},
               retest={'level':round(level,5),'time':m15[-1]['time'],'confirmed':True,'first_retest':True},
               checks={'htf_trend':True,'h1_confirmed_pivot':True,'m15_closed_breakout':True,
                       'm15_first_retest':True,'m5_candle_confirmed':True,'observed_target':True,
                       'entry_deviation':True,'rr_min_1_40':True},
               evidence={'bias_h4':b4,'bias_h1':b1,'bias_m30':b30,'level':round(level,5),
                         'atr_m15':round(a15,5),'atr_m5':round(a5,5),
                         'candle_pattern':pattern,'target_from_observed_h1':True,
                         'confidence_is_win_probability':False})
    return out
