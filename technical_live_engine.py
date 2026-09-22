"""Independent closed-candle, fail-closed XAUUSD technical signal scanner.

H1 EMA50/200 -> M15 confirmed support/resistance -> M5 candle, EMA50, RSI14.
This module has no network, database, AI or broker side effects. All levels must
come from observed OHLC and trade geometry must satisfy RR >= 1.40.
"""
from __future__ import annotations
from candle_diagnostics import attach_candle_diagnostics
import math
import time
from ict_engine import _ema, _atr, TF_SECONDS

MIN_RR = 1.40


def rsi14(bars):
    changes=[bars[i]['close']-bars[i-1]['close'] for i in range(len(bars)-14,len(bars))]
    gain=sum(max(c,0) for c in changes)/14
    loss=sum(max(-c,0) for c in changes)/14
    if gain == 0 and loss == 0:return 50.0
    if loss == 0:return 100.0
    return 100-(100/(1+gain/loss))


def pivots(bars,field,radius=2):
    results=[]
    for i in range(radius,len(bars)-radius):
        price=bars[i][field]
        around=[b[field] for b in bars[i-radius:i+radius+1]]
        if (price == min(around) if field=='low' else price == max(around)) and around.count(price)==1:
            results.append((i,price))
    return results


def analyze_technical_live(frames, *, live_price=None, now=None, min_rr=MIN_RR):
    now=time.time() if now is None else float(now)
    m5=frames.get('5min') or []
    out={'module_id':'technical_analysis_v2','source':'Texnik Analysis','signal':'WAIT',
         'state':'WAIT','reason':'INSUFFICIENT_CLOSED_CANDLES','confidence':0,
         'entry':None,'stop_loss':None,'take_profit':[],'risk_reward':None,
         'candle_time':str(m5[-1]['time']) if m5 else '', 'bias':'NEUTRAL',
         'ema50':None,'ema200':None,'ema50_m5':None,'rsi14':None,'atr_m5':None,
         'zone':None,'target_level':None,'candle_pattern':'NONE','checks':{},
         'model':'Closed H1 EMA50/200 -> M15 confirmed S/R -> M5 candle + EMA50 + RSI14'}
    def wait(reason):
        out['reason']=reason
        return out
    needs=(('1h',215),('15min',95),('5min',85))
    if any(len(frames.get(tf) or []) < n for tf,n in needs):return attach_candle_diagnostics(wait("INSUFFICIENT_CLOSED_CANDLES"), frames, (('1h', 215), ('15min', 95), ('5min', 85)))
    for tf,_ in needs:
        b=frames[tf]
        if any(b[i]['time']<=b[i-1]['time'] for i in range(1,len(b))):return wait('NON_MONOTONIC_CANDLES')
        if b[-1]['time']+TF_SECONDS[tf]>now:return wait('UNFINISHED_CANDLE')
        if now-(b[-1]['time']+TF_SECONDS[tf]) > (360 if tf=='5min' else 2.5*TF_SECONDS[tf]):
            return wait('STALE_'+tf.upper()+'_CANDLE')
    if live_price is None:return wait('LIVE_PRICE_UNAVAILABLE')
    try:entry=float(live_price)
    except (TypeError,ValueError,OverflowError):return wait('LIVE_PRICE_UNAVAILABLE')
    if not math.isfinite(entry) or entry<=0:return wait('LIVE_PRICE_UNAVAILABLE')
    h1=frames['1h'];m15=frames['15min'];last=m5[-1];prev=m5[-2]
    atr5=_atr(m5);atr15=_atr(m15)
    if not all(math.isfinite(a) and a>0 for a in (atr5,atr15)):return wait('INVALID_ATR')
    if abs(entry-last['close']) > max(.30*atr5,entry*.00010):return wait('ENTRY_DEVIATION_TOO_LARGE')
    ema50=_ema([b['close'] for b in h1],50);ema200=_ema([b['close'] for b in h1],200)
    ema5=_ema([b['close'] for b in m5],50)
    rsi=rsi14(m5)
    out.update(ema50=round(ema50,5),ema200=round(ema200,5),ema50_m5=round(ema5,5),
               rsi14=round(rsi,2),atr_m5=round(atr5,5))
    bias=('BULLISH' if h1[-1]['close']>ema50>ema200 else
          'BEARISH' if h1[-1]['close']<ema50<ema200 else 'NEUTRAL')
    out['bias']=bias
    if bias=='NEUTRAL':return wait('NO_H1_EMA_TREND')
    # Use only previously confirmed M15 pivots. The latest two bars are excluded
    # from pivot discovery so an unfinished right wing cannot repaint a zone.
    supports=pivots(m15[:-1],'low')
    resistances=pivots(m15[:-1],'high')
    if not supports or not resistances:return wait('NO_CONFIRMED_M15_LEVELS')
    tolerance=max(atr5*.22,entry*.000025)
    pattern='NONE';direction='BUY' if bias=='BULLISH' else 'SELL'
    bullish_engulf=(prev['close']<prev['open'] and last['close']>last['open']
        and last['open']<=prev['close'] and last['close']>=prev['open'])
    bearish_engulf=(prev['close']>prev['open'] and last['close']<last['open']
        and last['open']>=prev['close'] and last['close']<=prev['open'])
    body=max(abs(last['close']-last['open']),atr5*.04)
    lower=max(0,min(last['close'],last['open'])-last['low'])
    upper=max(0,last['high']-max(last['close'],last['open']))
    bull_pin=(last['close']>last['open'] and lower>=body*1.6 and upper<=body*1.2)
    bear_pin=(last['close']<last['open'] and upper>=body*1.6 and lower<=body*1.2)
    if direction=='BUY':
        if not (45<=rsi<=70 and entry>ema5):return wait('M5_EMA_RSI_CONFLICT')
        if bullish_engulf:pattern='BULLISH_ENGULFING'
        elif bull_pin:pattern='BULLISH_PIN_BAR'
        else:return wait('M5_CANDLE_NOT_CONFIRMED')
        levels=[p for i,p in supports if p <= last['high']+tolerance and last['low'] <= p+tolerance]
        # Price must close back above support after testing it.
        levels=[p for p in levels if last['close'] > p+tolerance*.15]
    else:
        if not (30<=rsi<=55 and entry<ema5):return wait('M5_EMA_RSI_CONFLICT')
        if bearish_engulf:pattern='BEARISH_ENGULFING'
        elif bear_pin:pattern='BEARISH_PIN_BAR'
        else:return wait('M5_CANDLE_NOT_CONFIRMED')
        levels=[p for i,p in resistances if p >= last['low']-tolerance and last['high'] >= p-tolerance]
        levels=[p for p in levels if last['close'] < p-tolerance*.15]
    out['candle_pattern']=pattern
    if not levels:return wait('M15_SUPPORT_RESISTANCE_NOT_RETESTED')
    # Choose the nearest eligible touched pivot, not a far level selected to force RR.
    level=min(levels,key=lambda p:abs(last['close']-p))
    buffer=max(.12*atr5,entry*.000020)
    if direction=='BUY':
        stop=min(level,last['low'])-buffer
        targets=sorted({b['high'] for b in h1[-105:] if b['high']>entry+tolerance})
        # The nearest opposing historical H1 high is the first roadblock.
        tp=targets[0] if targets else None
        risk=entry-stop;reward=(tp-entry) if tp is not None else -1
    else:
        stop=max(level,last['high'])+buffer
        targets=sorted({b['low'] for b in h1[-105:] if b['low']<entry-tolerance},reverse=True)
        tp=targets[0] if targets else None
        risk=stop-entry;reward=(entry-tp) if tp is not None else -1
    out['zone']={'type':'SUPPORT' if direction=='BUY' else 'RESISTANCE',
                 'level':round(level,5),'low':round(level-tolerance,5),'high':round(level+tolerance,5)}
    if tp is None or risk<=0 or reward<=0:return wait('NO_OBSERVED_H1_TARGET')
    rr=reward/risk
    if not math.isfinite(rr) or not (max(MIN_RR,float(min_rr))-1e-9<=rr<=6.0):return wait('TARGET_RR_OUT_OF_RANGE')
    if not all(math.isfinite(x) and x>0 for x in (stop,tp)):return wait('INVALID_TRADE_GEOMETRY')
    if not ((stop<entry<tp) if direction=='BUY' else (tp<entry<stop)):return wait('INVALID_TRADE_GEOMETRY')
    out.update(signal=direction,state='READY',reason='Closed H1 trend, M15 zone, M5 candle/EMA/RSI and observed H1 target',
               confidence=88 if 'ENGULFING' in pattern else 86,
               entry=round(entry,5),stop_loss=round(stop,5),take_profit=[round(tp,5)],
               risk_reward=round(rr,4),target_level=round(tp,5),
               checks={'h1_trend':True,'m15_zone':True,'m5_candle_confirmed':True,'ema50_alignment':True,
                       'rsi14_alignment':True,'observed_h1_target':True,'fresh_closed_candles':True,
                       'entry_deviation':True,'rr_min_1_40':True},
               evidence={'trend_h1':bias,'ema50_h1':round(ema50,5),'ema200_h1':round(ema200,5),
                         'ema50_m5':round(ema5,5),'rsi14_m5':round(rsi,2),'candle_pattern':pattern,
                         'support_resistance_level':round(level,5),'target_from_observed_h1':True,
                         'confidence_is_win_probability':False})
    return out
