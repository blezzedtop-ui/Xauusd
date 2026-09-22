"""Closed-candle XAU/USD trendline signal scanner. No AI, orders, or persistence.

Confirmed 3/3 swing anchors, third-touch bounce or breakout then first retest.
Only observed H1 price targets are used; RR is never forced by inventing TP.
"""
from __future__ import annotations
from candle_diagnostics import attach_candle_diagnostics
import math
import time
from ict_engine import _atr, _bias, TF_SECONDS

MIN_RR = 1.40


def confirmed_swings(bars, kind, radius=3, lookback=105):
    field='low' if kind=='low' else 'high'
    points=[]
    for j in range(max(radius,len(bars)-lookback),len(bars)-radius):
        window=bars[j-radius:j+radius+1]
        value=bars[j][field]
        if (value==min(x[field] for x in window) if kind=='low' else value==max(x[field] for x in window)) and sum(x[field]==value for x in window)==1:
            points.append({'idx':j,'time':bars[j]['time'],'price':value})
    return points


def analyze_trendline_live(frames, *, live_price=None, now=None, min_rr=MIN_RR):
    now=time.time() if now is None else float(now)
    m5=frames.get('5min') or []
    out={'module_id':'trendline_analysis','source':'Trendline Analysis','signal':'WAIT',
         'state':'WAIT','reason':'INSUFFICIENT_CLOSED_CANDLES','confidence':0,
         'entry':None,'stop_loss':None,'take_profit':[],'risk_reward':None,
         'candle_time':str(m5[-1]['time']) if m5 else '', 'bias':'NEUTRAL',
         'trendlines':[],'trendline':None,'checks':{},
         'model':'Confirmed M5 3/3 swings → third touch or breakout + first retest; M30/H1 trend'}
    def wait(reason,state='WAIT'):
        out.update(reason=reason,state=state)
        return out
    needs=(('4h',55),('1h',65),('30min',65),('15min',35),('5min',105))
    if any(len(frames.get(tf) or [])<minimum for tf,minimum in needs):return attach_candle_diagnostics(wait("INSUFFICIENT_CLOSED_CANDLES"), frames, (('4h', 55), ('1h', 65), ('30min', 65), ('15min', 35), ('5min', 105)))
    for tf,_ in needs:
        seq=frames[tf]
        if any(seq[i]['time']<=seq[i-1]['time'] for i in range(1,len(seq))):return wait('NON_MONOTONIC_CANDLES')
        if now < seq[-1]['time']+TF_SECONDS[tf]:return wait('UNFINISHED_CANDLE')
        if now-(seq[-1]['time']+TF_SECONDS[tf])> (360 if tf=='5min' else 2.5*TF_SECONDS[tf]):
            return wait('STALE_'+tf.upper()+'_CANDLE')
    if live_price is None:return wait('LIVE_PRICE_UNAVAILABLE')
    try:entry=float(live_price)
    except (ValueError,TypeError,OverflowError):return wait('LIVE_PRICE_UNAVAILABLE')
    if not math.isfinite(entry) or entry<=0:return wait('LIVE_PRICE_UNAVAILABLE')
    atr=_atr(m5)
    if not math.isfinite(atr) or atr<=0:return wait('INVALID_ATR')
    last=m5[-1]
    if abs(entry-last['close'])>max(.30*atr,entry*.00010):return wait('ENTRY_DEVIATION_TOO_LARGE')
    h4,h1,m30=(frames[tf] for tf in ('4h','1h','30min'))
    bias4,bias1,bias30=(_bias(b) for b in (h4,h1,m30))
    out['bias']=bias30
    tol=max(.16*atr,entry*.000015)
    candidates=[]
    # Each slope is constructed from pivots already confirmed before the trigger candle.
    for kind in ('low','high'):
        points=confirmed_swings(m5[:-1],kind)
        for second in reversed(points[-7:]):
            for first in reversed([p for p in points if 7<=second['idx']-p['idx']<=80][-6:]):
                slope=(second['price']-first['price'])/(second['idx']-first['idx'])
                ascending=kind=='low' and slope>0
                descending=kind=='high' and slope<0
                if not (ascending or descending) or abs(slope)> .6*atr:continue
                line=lambda i: first['price']+slope*(i-first['idx'])
                n=len(m5)-1
                current=line(n)
                if abs(current-entry)>10*atr:continue
                invalidation=sum((bar['close']<line(j)-tol if ascending else bar['close']>line(j)+tol)
                                  for j,bar in enumerate(m5[second['idx']+1:-1],second['idx']+1))
                # A line that is repeatedly broken before the setup is no longer a valid bounce line.
                intact=invalidation==0
                is_bullish=ascending
                bounce_dir='BUY' if ascending else 'SELL'
                if ascending:
                    bounce=(intact and last['low']<=current+tol and last['close']>current+tol*.25
                            and last['close']>last['open'] and last['close']>m5[-2]['close'])
                    wick=max(0,min(last['open'],last['close'])-last['low'])
                else:
                    bounce=(intact and last['high']>=current-tol and last['close']<current-tol*.25
                            and last['close']<last['open'] and last['close']<m5[-2]['close'])
                    wick=max(0,last['high']-max(last['open'],last['close']))
                body=max(abs(last['close']-last['open']),.08*atr)
                bounce=bounce and wick>=.25*body
                # 2 confirmed pivots + FIRST new interaction after the second pivot was known.
                earlier=m5[second['idx']+4:n]
                used=any((b['low']<=line(j)+tol if ascending else b['high']>=line(j)-tol)
                         for j,b in enumerate(earlier,second['idx']+4))
                if bounce and not used:
                    candidates.append((bounce_dir,'THIRD_TOUCH',first,second,current,slope,kind,92))
                # Breakout must be a closed body 2-7 bars ago, then first retest now.
                breaks=[]
                for j in range(max(second['idx']+4,n-7),n-1):
                    bar=m5[j]
                    crossed=((bar['close']<line(j)-tol and bar['open']>=line(j)-tol)
                             if ascending else (bar['close']>line(j)+tol and bar['open']<=line(j)+tol))
                    if crossed and abs(bar['close']-bar['open'])>=.65*atr:breaks.append(j)
                if breaks:
                    j=breaks[-1]
                    post=m5[j+1:n]
                    crossed_again=any((b['low']<=line(k)+tol if ascending else b['high']>=line(k)-tol)
                                      for k,b in enumerate(post,j+1))
                    retest=(last['high']>=current-tol and last['close']<current-tol*.25 and last['close']<last['open']
                            if ascending else last['low']<=current+tol and last['close']>current+tol*.25 and last['close']>last['open'])
                    if retest and not crossed_again:
                        reversal_wick=(max(0,last['high']-max(last['open'],last['close'])) if ascending
                                       else max(0,min(last['open'],last['close'])-last['low']))
                        if reversal_wick>=.25*body:
                            candidates.append(('SELL' if ascending else 'BUY','BREAKOUT_RETEST',first,second,current,slope,kind,89))
    if not candidates:return wait('NO_CONFIRMED_TRENDLINE_REACTION')
    out['trendlines']=[{'direction':d,'pattern':pattern,'anchor_1':p1,'anchor_2':p2,
                        'price':round(price,5)} for d,pattern,p1,p2,price,_,_,_ in candidates[:8]]
    filtered=[]
    for direction,pattern,p1,p2,price,slope,kind,score in candidates:
        htf='BULLISH' if direction=='BUY' else 'BEARISH'
        opposite='BEARISH' if direction=='BUY' else 'BULLISH'
        if bias30!=htf or bias1==opposite or bias4==opposite:continue
        if pattern=='THIRD_TOUCH' and (last['low'] < price-2.5*tol if direction=='BUY' else last['high'] > price+2.5*tol):continue
        buffer=max(.15*atr,entry*.000025)
        if direction=='BUY':
            stop=min(last['low'],price, m5[-2]['low'])-buffer
            targets=sorted({x['high'] for x in h1[-65:] if x['high']>entry+tol})
            target=targets[0] if targets else None
            risk=entry-stop;reward=target-entry if target else -1
        else:
            stop=max(last['high'],price,m5[-2]['high'])+buffer
            targets=sorted({x['low'] for x in h1[-65:] if x['low']<entry-tol},reverse=True)
            target=targets[0] if targets else None
            risk=stop-entry;reward=entry-target if target else -1
        if target is None or risk<=0 or reward<=0:continue
        rr=reward/risk
        if not (max(MIN_RR,float(min_rr))-1e-9<=rr<=6):continue
        if not all(math.isfinite(x) and x>0 for x in (entry,stop,target)):continue
        # Latest, most tightly confirmed anchor is preferred over scanning a very old line.
        filtered.append((p2['idx'],score,rr,direction,pattern,p1,p2,price,slope,kind,stop,target))
    if not filtered:return wait('WAIT_HTF_TARGET_OR_RR_CONFIRMATION','WAIT_CONFIRMATION')
    if len({v[3] for v in filtered})>1:return wait('CONFLICTING_TRENDLINE_DIRECTIONS')
    _,score,rr,direction,pattern,p1,p2,price,slope,kind,stop,target=max(filtered,key=lambda v:(v[0],v[1],v[2]))
    out.update(signal=direction,state='READY',reason='Confirmed swing trendline, closed-candle '+pattern+', observed H1 target',
               confidence=score,entry=round(entry,5),stop_loss=round(stop,5),take_profit=[round(target,5)],
               risk_reward=round(rr,4),pattern=pattern,
               trendline={'type':'ASCENDING' if kind=='low' else 'DESCENDING','touches':3 if pattern=='THIRD_TOUCH' else 2,
                          'anchor_1':p1,'anchor_2':p2,'price':round(price,5),'slope_per_m5':round(slope,7),
                          'confirmed':True,'pattern':pattern,'closed_candle_confirmed':True},
               checks={'confirmed_swings':True,'closed_candle_reaction':True,'htf_alignment':True,'observed_target':True,
                       'entry_deviation':True,'rr_min_1_40':True},
               evidence={'atr_m5':round(atr,5),'bias_h4':bias4,'bias_h1':bias1,'bias_m30':bias30,
                         'target_from_observed_h1':True,'confidence_is_win_probability':False})
    return out
