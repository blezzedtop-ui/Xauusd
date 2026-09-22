"""Independent XAUUSD Order Block scanner. Pure, closed-candle logic; NO trading side effects.

Confirmed historical swing -> closed M15 BOS + >=1.5 ATR displacement -> fresh
opposite M15 candle -> FIRST closed M5 retest/rejection -> observed target -> RR.
This identifies price-action zones, not actual institutional resting orders.
"""
from __future__ import annotations
from candle_diagnostics import attach_candle_diagnostics
import math
import time
from ict_engine import TF_SECONDS, _atr, _bias

MIN_RR = 1.40


def confirmed_pivots(bars, end, *, radius=3, lookback=95):
    """Pivot is known only once its three candles to the right have closed."""
    highs, lows = [], []
    for j in range(max(radius, end-lookback), end-radius):
        slice_ = bars[j-radius:j+radius+1]
        if len(slice_) != 2*radius+1:
            continue
        high,low = bars[j]['high'],bars[j]['low']
        if sum(x['high']==high for x in slice_)==1 and high==max(x['high'] for x in slice_):
            highs.append({'price':high,'time':bars[j]['time']})
        if sum(x['low']==low for x in slice_)==1 and low==min(x['low'] for x in slice_):
            lows.append({'price':low,'time':bars[j]['time']})
    return highs, lows


def analyze_order_block_live(frames, *, live_price=None, now=None, min_rr=MIN_RR):
    now=time.time() if now is None else float(now)
    m5=frames.get('5min') or []
    out={'module_id':'order_block','source':'Order Block Analysis','signal':'WAIT',
         'state':'WAIT','reason':'INSUFFICIENT_CLOSED_CANDLES','confidence':0,'score':0,
         'entry':None,'stop_loss':None,'take_profit':[],'risk_reward':None,
         'candle_time':str(m5[-1]['time']) if m5 else '', 'bias':'NEUTRAL',
         'order_block':None,'blocks':[],'checks':{},
         'model':'M15 OB + confirmed BOS / displacement → first M5 retest / rejection'}
    def wait(reason,state='WAIT'):
        out.update(reason=reason,state=state)
        return out
    needed=(('4h',55),('1h',80),('15min',95),('5min',100))
    if any(len(frames.get(tf) or [])<n for tf,n in needed):
        return attach_candle_diagnostics(wait("INSUFFICIENT_CLOSED_CANDLES"), frames, (('4h', 55), ('1h', 80), ('15min', 95), ('5min', 100)))
    if any(any(bar['time']<=seq[i-1]['time'] for i,bar in enumerate(seq[1:],1))
           for seq in (frames[tf] for tf,_ in needed)):
        return wait('NON_MONOTONIC_CANDLES')
    if now < m5[-1]['time']+300 or now-(m5[-1]['time']+300)>360:
        return wait('STALE_M5_CANDLE')
    if any(now-(frames[tf][-1]['time']+TF_SECONDS[tf])>2.5*TF_SECONDS[tf]
           for tf in ('4h','1h','15min')):
        return wait('STALE_HIGHER_TIMEFRAME')
    if live_price is None:
        return wait('LIVE_PRICE_UNAVAILABLE')
    try: entry=float(live_price)
    except (TypeError,ValueError,OverflowError):return wait('LIVE_PRICE_UNAVAILABLE')
    if not math.isfinite(entry) or entry<=0:
        return wait('LIVE_PRICE_UNAVAILABLE')
    h4,h1,m15=(frames[tf] for tf in ('4h','1h','15min'))
    a5,a15=_atr(m5),_atr(m15)
    if not (math.isfinite(a5) and a5>0 and math.isfinite(a15) and a15>0):
        return wait('INVALID_ATR')
    if abs(entry-m5[-1]['close'])>max(.3*a5,entry*.0001):
        return wait('ENTRY_DEVIATION_TOO_LARGE')
    b4,b1=_bias(h4),_bias(h1)
    out['bias']=b1
    # Current closed M5 must be the confirmation. No future candles are read.
    last=m5[-1];prev=m5[-2]
    tol=max(a5*.14,entry*.000015)
    candidates=[];found=[]
    # A <= 12-candle old M15 impulse prevents long-lived / stale order blocks.
    for i in range(len(m15)-2,max(25,len(m15)-15),-1):
        impulse=m15[i]
        prior=m15[max(0,i-17):i]
        atr_pre=_atr(m15[:i])
        if atr_pre<=0:continue
        body=abs(impulse['close']-impulse['open'])
        if body < 1.5*atr_pre:continue
        hi,lo=confirmed_pivots(m15,i)
        if not hi and not lo:continue
        swing_high=hi[-1]['price'] if hi else math.inf
        swing_low=lo[-1]['price'] if lo else -math.inf
        direction=('BUY' if hi and impulse['close']>impulse['open'] and impulse['close']>swing_high
                   else 'SELL' if lo and impulse['close']<impulse['open'] and impulse['close']<swing_low
                   else None)
        if not direction:continue
        # The last opposite candle must PRECEDE the impulse and have existed at detection time.
        opposite=next((j for j in range(i-1,max(-1,i-6),-1)
            if (m15[j]['close']<m15[j]['open'] if direction=='BUY'
                else m15[j]['close']>m15[j]['open'])),None)
        if opposite is None:continue
        candle=m15[opposite];zlo,zhi=candle['low'],candle['high']
        if not (0<zhi-zlo<=2.8*atr_pre):continue
        bos_level=swing_high if direction=='BUY' else swing_low
        # Zones become invalid when subsequent closed M15 candles close beyond their edge.
        later=[x for x in m15[i+1:] if x['time']+900<last['time']]
        invalid=any(x['close']<zlo-tol if direction=='BUY' else x['close']>zhi+tol for x in later)
        # Strict first retest after the impulse: if a prior closed M5 has intersected the
        # original zone, this setup cannot be recycled on a later candle.
        first_after=impulse['time']+900
        earlier=[x for x in m5[:-1] if first_after<=x['time']<last['time']]
        touched_before=any(x['low']<=zhi+tol and x['high']>=zlo-tol for x in earlier)
        fvg=(m15[i-2]['high'] < impulse['low'] if direction=='BUY'
             else m15[i-2]['low'] > impulse['high'])
        block={'direction':direction,'low':round(zlo,5),'high':round(zhi,5),
               'time':candle['time'],'impulse_time':impulse['time'],
               'bos_level':round(bos_level,5),'displacement_atr':round(body/atr_pre,3),
               'bos':True,'fvg':fvg,'fresh':not (invalid or touched_before),
               'invalidated':invalid,'previously_touched':touched_before}
        found.append(block)
        if invalid or touched_before:continue
        htf='BULLISH' if direction=='BUY' else 'BEARISH'
        if b1!=htf or b4 not in (htf,'NEUTRAL'):continue
        # Prior M5 candle must not have closed through the invalidation boundary.
        if direction=='BUY':
            touch=last['low']<=zhi+tol and last['high']>=zlo-tol
            wick=max(0,min(last['open'],last['close'])-last['low'])
            body5=max(abs(last['close']-last['open']),.08*a5)
            confirm=(touch and last['close']>last['open'] and last['close']>zhi
                     and last['close']>prev['close'] and wick>=.30*body5
                     and prev['close']>=zlo-tol)
        else:
            touch=last['high']>=zlo-tol and last['low']<=zhi+tol
            wick=max(0,last['high']-max(last['open'],last['close']))
            body5=max(abs(last['close']-last['open']),.08*a5)
            confirm=(touch and last['close']<last['open'] and last['close']<zlo
                     and last['close']<prev['close'] and wick>=.30*body5
                     and prev['close']<=zhi+tol)
        if not confirm:continue
        if last['high']-last['low']>3.5*a5:continue
        if abs(entry-last['close'])>max(.3*a5,entry*.0001):continue
        if direction=='BUY':
            stop=min(zlo,last['low'])-max(.15*a5,entry*.000025)
            # Observed HTF liquidity target (not an invented RR extension).
            targets=sorted({x['high'] for x in h1[-80:] if x['high']>entry+tol})
            target=targets[0] if targets else None
            risk=entry-stop;reward=target-entry if target else -1
        else:
            stop=max(zhi,last['high'])+max(.15*a5,entry*.000025)
            targets=sorted({x['low'] for x in h1[-80:] if x['low']<entry-tol},reverse=True)
            target=targets[0] if targets else None
            risk=stop-entry;reward=entry-target if target else -1
        if not target or not risk>0 or not reward>0:continue
        rr=reward/risk
        if not (max(MIN_RR,float(min_rr))-1e-9<=rr<=6):continue
        if not all(math.isfinite(x) and x>0 for x in (entry,stop,target)):continue
        score=min(98,86+4*(b4==htf)+4*int(fvg)+min(4,int(body/atr_pre)))
        candidates.append((score,rr,direction,block,stop,target))
    out['blocks']=found[:8]
    if not candidates:
        if any(b['fresh'] for b in found):return wait('WAIT_RETEST_OR_HTF_RR_CONFIRMATION','WAIT_RETEST')
        if found:return wait('OB_INVALIDATED_OR_EXPIRED','OB_INVALIDATED')
        return wait('NO_CONFIRMED_OB_BOS_DISPLACEMENT')
    if len({x[2] for x in candidates})>1:
        return wait('CONFLICTING_ORDER_BLOCK_DIRECTIONS')
    score,rr,direction,block,stop,target=max(candidates,key=lambda x:(x[0],x[1]))
    out.update(signal=direction,state='READY',
               reason='Fresh M15 OB + closed BOS/displacement + first M5 retest and rejection; observed H1 target',
               confidence=score,score=score,order_block=block,
               entry=round(entry,5),stop_loss=round(stop,5),take_profit=[round(target,5)],
               risk_reward=round(rr,4),
               checks={'bos_confirmed':True,'displacement_confirmed':True,'fresh_ob':True,
                       'm5_closed_retest':True,'higher_timeframe_agrees':True,'rr_min_1_40':True},
               evidence={'atr_m5':round(a5,5),'atr_m15':round(a15,5),'bias_h1':b1,'bias_h4':b4,
                         'observed_target':True,'score_is_win_probability':False})
    return out
