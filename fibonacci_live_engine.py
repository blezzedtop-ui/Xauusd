"""Fibonacci retracement signals using ONLY closed candles; AI/MT5 outside engine.

ICT stays independent. No implicit fallback, no manufactured levels to meet RR.
"""
from __future__ import annotations
from candle_diagnostics import attach_candle_diagnostics
import math
import time
from fibonacci_strategy import _atr, _swings, _trend
from ict_engine import TF_SECONDS, _bias

MIN_RR=1.40

def analyze_fibonacci_live(bars_by_tf, *, live_price=None, now=None, min_rr=MIN_RR):
    now=time.time() if now is None else float(now)
    candles=bars_by_tf.get('15min') or []
    out={'module_id':'fibonacci','source':'Fibonacci','signal':'WAIT','state':'WAIT','reason':'INSUFFICIENT_CLOSED_CANDLES',
         'confidence':0,'score':0,'entry':None,'stop_loss':None,'take_profit':[],'risk_reward':None,
         'candle_time':str(candles[-1]['time']) if candles else '', 'trend':'NEUTRAL',
         'levels':{},'extension':{},'swing':{},'checks':{},'model':'Confirmed swing → 0.500–0.618 retest → closed-candle confirmation'}
    def wait(reason):
        out['reason']=reason
        return out
    if any(len(bars_by_tf.get(tf) or []) < n for tf,n in (('4h',55),('1h',65),('15min',90))):
        return attach_candle_diagnostics(wait("INSUFFICIENT_CLOSED_CANDLES"), bars_by_tf, (('4h', 55), ('1h', 65), ('15min', 90)))
    if now-(candles[-1]['time']+900)>960:
        return wait('STALE_M15_CANDLE')
    if any(now-(bars_by_tf[tf][-1]['time']+TF_SECONDS[tf])>2.5*TF_SECONDS[tf] for tf in ('4h','1h')):
        return wait('STALE_HIGHER_TIMEFRAME')
    if live_price is None or not math.isfinite(float(live_price)) or float(live_price)<=0:
        return wait('LIVE_PRICE_UNAVAILABLE')
    higher=[_bias(bars_by_tf[tf]) for tf in ('4h','1h')]
    if higher[1] not in ('BULLISH','BEARISH') or higher[0] not in (higher[1],'NEUTRAL'):
        return wait('HTF_TREND_NOT_ALIGNED')
    trend=higher[1]
    out['trend']=trend
    work=candles[-180:]
    highs,lows=_swings(work)
    if len(highs)<2 or len(lows)<2:
        return wait('SWING_UNCONFIRMED')
    # Use last confirmed complete directional A→B leg; do not use the unfinished bar as anchor.
    if trend=='BULLISH':
        endpoints=[(i,v) for i,v in highs if i <= len(work)-4 and any(lo_i<i for lo_i,_ in lows)]
        if not endpoints: return wait('NO_CONFIRMED_SWING')
        bi,bv=endpoints[-1]
        origins=[(i,v) for i,v in lows if i<bi and bi-i<=90]
        if not origins:return wait('NO_SWING_ORIGIN')
        ai,av=origins[-1]
    else:
        endpoints=[(i,v) for i,v in lows if i <= len(work)-4 and any(hi_i<i for hi_i,_ in highs)]
        if not endpoints: return wait('NO_CONFIRMED_SWING')
        bi,bv=endpoints[-1]
        origins=[(i,v) for i,v in highs if i<bi and bi-i<=90]
        if not origins:return wait('NO_SWING_ORIGIN')
        ai,av=origins[-1]
    atr=_atr(work)
    distance=abs(bv-av)
    if not math.isfinite(atr) or atr<=0 or distance<max(atr*3,float(live_price)*0.0005):
        return wait('SWING_TOO_SMALL')
    retrace=lambda r: bv-distance*r if trend=='BULLISH' else bv+distance*r
    project=lambda r: av+distance*r if trend=='BULLISH' else av-distance*r
    out['swing']={'a_index':ai,'a_price':round(av,5),'b_index':bi,'b_price':round(bv,5)}
    out['levels']={str(r):round(retrace(r),5) for r in (.382,.5,.618,.705,.786)}
    out['extension']={str(r):round(project(r),5) for r in (1.272,1.618)}
    zone_low=min(retrace(.5),retrace(.618));zone_high=max(retrace(.5),retrace(.618))
    last=work[-1]; prior=work[-2]
    tol=max(.12*atr,live_price*.000025)
    touches=last['low']<=zone_high+tol and last['high']>=zone_low-tol
    out['checks']['fib_zone']=bool(touches)
    if not touches:return wait('AWAITING_0500_0618_RETEST')
    # The confirmation candle must close back toward the impulse, not just touch Fibonacci.
    midpoint=(zone_low+zone_high)/2
    confirmed=(last['close']>last['open'] and last['close']>midpoint and last['close']>=prior['close']) if trend=='BULLISH' else (last['close']<last['open'] and last['close']<midpoint and last['close']<=prior['close'])
    out['checks']['closed_candle_confirmation']=bool(confirmed)
    if not confirmed:return wait('CANDLE_CONFIRMATION_PENDING')
    entry=float(live_price)
    if abs(entry-last['close'])>max(.28*atr,entry*.00012):
        return wait('ENTRY_DEVIATION_TOO_LARGE')
    stop=min(av,min(x['low'] for x in work[bi+1:]))-.12*atr if trend=='BULLISH' else max(av,max(x['high'] for x in work[bi+1:]))+.12*atr
    target1=project(1.272);target2=project(1.618)
    risk=entry-stop if trend=='BULLISH' else stop-entry
    reward=target1-entry if trend=='BULLISH' else entry-target1
    if risk<=0 or not all(math.isfinite(v) and v>0 for v in (entry,stop,target1,target2)):
        return wait('INVALID_STOP_TP_GEOMETRY')
    rr=reward/risk
    if rr<max(min_rr,MIN_RR)-1e-9 or rr>6 or risk>max(5*atr,entry*.005):
        return wait('RR_OR_RISK_NOT_ELIGIBLE')
    # Additional guard: the retracement must not cross the swing invalidation.
    if (trend=='BULLISH' and not stop<entry<target1<target2) or (trend=='BEARISH' and not target2<target1<entry<stop):
        return wait('INVALID_DIRECTIONAL_GEOMETRY')
    out.update({'signal':'BUY' if trend=='BULLISH' else 'SELL','state':'READY','confidence':90,'score':90,
        'entry':round(entry,5),'stop_loss':round(stop,5),'take_profit':[round(target1,5),round(target2,5)],
        'risk_reward':round(rr,4),'reason':'HTF aligned; closed M15 confirmation at 0.500–0.618 retracement; fixed 1.272 extension target',
        'checks':{**out['checks'],'mtf_aligned':True,'entry_fresh':True,'rr_min_1_40':True},
        'evidence':{'candle_time':last['time'],'swing_start_time':work[ai]['time'],'swing_end_time':work[bi]['time'],
                    'retracement_zone':[round(zone_low,5),round(zone_high,5)],'atr':round(atr,5),
                    'htf':{'H4':higher[0],'H1':higher[1]},'target_policy':'fixed_1.272_extension'}})
    return out
