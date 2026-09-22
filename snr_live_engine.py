"""Closed-candle SNR engine for XAU/USD. No API calls or trading side effects.

Confirmed H1 pivot clusters form support/resistance zones; M5 supplies the
closed-candle bounce or breakout/retest. Observed opposing zones are TP targets.
All missing evidence is WAIT. A heuristic score is NOT a win probability.
"""
from __future__ import annotations
import math
import time
from ict_engine import TF_SECONDS, _atr, _bias

MIN_RR = 1.40


def detect_zones(h1, *, atr=None, radius=2, min_touches=2):
    """Only structurally confirmed pivots, clustered into price zones."""
    if len(h1) < 45:
        return {'support': [], 'resistance': []}
    atr = _atr(h1) if atr is None else float(atr)
    if not math.isfinite(atr) or atr <= 0:
        return {'support': [], 'resistance': []}
    tolerance = max(atr * .48, float(h1[-1]['close']) * .00008)
    output = {}
    for kind, field, extreme in (('support', 'low', min), ('resistance', 'high', max)):
        pivots = []
        for i in range(radius, len(h1)-radius):
            p = float(h1[i][field])
            window = [float(h1[j][field]) for j in range(i-radius, i+radius+1)]
            if p == extreme(window) and (window.count(p) == 1):
                pivots.append((i, p))
        clusters = []
        for i, p in pivots:
            matches = [c for c in clusters if abs(p - c['center']) <= tolerance]
            if matches:
                c = min(matches, key=lambda z: abs(p-z['center']))
                if i - c['indexes'][-1] < radius*2 + 1:
                    continue
                c['indexes'].append(i)
                c['points'].append(p)
                c['center'] = sum(c['points']) / len(c['points'])
            else:
                clusters.append({'center': p, 'indexes': [i], 'points': [p]})
        zones = []
        for c in clusters:
            if len(c['points']) < min_touches:
                continue
            low = min(c['points']) - .16 * atr
            high = max(c['points']) + .16 * atr
            # Reject huge merged ranges, which no longer constitute an actionable zone.
            if high - low > 1.35 * atr:
                continue
            zones.append({'type': kind.upper(), 'low': round(low,5), 'high': round(high,5),
                          'center': round(c['center'],5), 'touches': len(c['points']),
                          'last_pivot_time': int(h1[c['indexes'][-1]]['time'])})
        output[kind] = sorted(zones, key=lambda z: z['center'])
    return output


def analyze_snr_live(bars_by_tf, *, live_price=None, now=None, min_rr=MIN_RR):
    now = time.time() if now is None else float(now)
    m5 = bars_by_tf.get('5min') or []
    out = {'module_id':'snr', 'source':'SNR Analysis', 'signal':'WAIT', 'state':'WAIT',
           'reason':'INSUFFICIENT_CLOSED_CANDLES', 'confidence':0, 'score':0,
           'entry':None, 'stop_loss':None, 'take_profit':[], 'risk_reward':None,
           'candle_time':str(m5[-1]['time']) if m5 else '', 'bias':'NEUTRAL',
           'setup':'NONE', 'zone':None, 'target_zone':None, 'zones':{},
           'checks':{}, 'model':'H1/H4 pivot zones → M15 context → M5 confirmed bounce/retest'}
    def wait(reason):
        out['reason'] = reason
        return out
    required = (('4h',55),('1h',105),('15min',55),('5min',90))
    if any(len(bars_by_tf.get(tf) or []) < count for tf,count in required):
        return wait('INSUFFICIENT_CLOSED_CANDLES')
    if any(any(x['time'] <= b[i-1]['time'] for i,x in enumerate(b[1:],1))
           for b in (bars_by_tf[tf] for tf,_ in required)):
        return wait('NON_MONOTONIC_CANDLES')
    if now-(m5[-1]['time']+TF_SECONDS['5min']) > 360 or m5[-1]['time']+300 > now:
        return wait('STALE_M5_CANDLE')
    if any(now-(bars_by_tf[tf][-1]['time']+TF_SECONDS[tf]) > 2.5*TF_SECONDS[tf]
           for tf in ('4h','1h','15min')):
        return wait('STALE_HIGHER_TIMEFRAME')
    if live_price is None:
        return wait('LIVE_PRICE_UNAVAILABLE')
    try:
        entry=float(live_price)
    except (ValueError,TypeError,OverflowError):
        return wait('LIVE_PRICE_UNAVAILABLE')
    if not math.isfinite(entry) or entry <= 0:
        return wait('LIVE_PRICE_UNAVAILABLE')
    h1=bars_by_tf['1h'];h4=bars_by_tf['4h'];m15=bars_by_tf['15min']
    atr5=_atr(m5);atr1=_atr(h1)
    if not all(math.isfinite(x) and x>0 for x in (atr5,atr1)):
        return wait('INVALID_ATR')
    if abs(entry-m5[-1]['close']) > max(.3*atr5, entry*.00010):
        return wait('ENTRY_DEVIATION_TOO_LARGE')
    b1,b4 = _bias(h1),_bias(h4)
    out['bias']=b1
    zones=detect_zones(h1,atr=atr1)
    out['zones']=zones
    if not zones['support'] or not zones['resistance']:
        return wait('UNCONFIRMED_SNR_ZONES')
    last=m5[-1];prev=m5[-2];preprev=m5[-3]
    tolerance=max(.17*atr5,entry*.000025)
    candidates=[]
    for kind in ('support','resistance'):
        for zone in zones[kind]:
            level_low=zone['low'];level_high=zone['high']
            if kind=='support':
                # Confirmed support bounce with a CLOSED bullish candle.
                touched=last['low']<=level_high+tolerance and last['high']>=level_low-tolerance
                close_ok=last['close']>last['open'] and last['close']>prev['close'] and last['close']>level_high
                wick=max(0,min(last['open'],last['close'])-last['low'])
                body=max(abs(last['close']-last['open']),.08*atr5)
                if touched and close_ok and wick>=.32*body:
                    candidates.append(('BUY','SUPPORT_BOUNCE',zone))
                # Support broken on a prior closed candle, then resistance retest.
                if (preprev['close']>=level_low and prev['close']<level_low-tolerance
                    and last['high']>=level_low-tolerance and last['close']<level_low
                    and last['close']<last['open'] and last['close']<=prev['close']):
                    candidates.append(('SELL','SUPPORT_BREAK_RETEST',zone))
            else:
                touched=last['high']>=level_low-tolerance and last['low']<=level_high+tolerance
                close_ok=last['close']<last['open'] and last['close']<prev['close'] and last['close']<level_low
                wick=max(0,last['high']-max(last['open'],last['close']))
                body=max(abs(last['close']-last['open']),.08*atr5)
                if touched and close_ok and wick>=.32*body:
                    candidates.append(('SELL','RESISTANCE_REJECTION',zone))
                if (preprev['close']<=level_high and prev['close']>level_high+tolerance
                    and last['low']<=level_high+tolerance and last['close']>level_high
                    and last['close']>last['open'] and last['close']>=prev['close']):
                    candidates.append(('BUY','RESISTANCE_BREAK_RETEST',zone))
    if not candidates:
        return wait('AWAITING_ZONE_REACTION_OR_RETEST')
    if last['high']-last['low'] > max(3.5*atr5, .9*atr1):
        return wait('EXTREME_CONFIRMATION_CANDLE')
    accepted=[]
    for direction,setup,zone in candidates:
        desired='BULLISH' if direction=='BUY' else 'BEARISH'
        if b1!=desired or b4 not in (desired,'NEUTRAL'):
            continue
        # M15 may still be retracing, but should not have closed beyond invalidation.
        if direction=='BUY' and m15[-1]['close']<zone['low']-.30*atr1:
            continue
        if direction=='SELL' and m15[-1]['close']>zone['high']+.30*atr1:
            continue
        if abs(entry-zone['center'])>max(2.5*atr5,1.5*atr1):
            continue
        if direction=='BUY':
            stop=min(zone['low'],last['low'])-max(.15*atr5, entry*.000025)
            opposing=[z for z in zones['resistance'] if z['low']>entry]
            target_zone=min(opposing,key=lambda z:z['low']) if opposing else None
            target=target_zone['low'] if target_zone else None
            risk=entry-stop
            reward=target-entry if target else -1
        else:
            stop=max(zone['high'],last['high'])+max(.15*atr5, entry*.000025)
            opposing=[z for z in zones['support'] if z['high']<entry]
            target_zone=max(opposing,key=lambda z:z['high']) if opposing else None
            target=target_zone['high'] if target_zone else None
            risk=stop-entry
            reward=entry-target if target else -1
        if not target_zone or not (risk>0 and reward>0):
            continue
        rr=reward/risk
        if not (max(float(min_rr),MIN_RR)-1e-9<=rr<=6 and risk<=max(5*atr1,entry*.005)):
            continue
        if not all(math.isfinite(x) and x>0 for x in (entry,stop,target)):
            continue
        quality=min(98,80+min(3,int(zone['touches']))*3+5)
        accepted.append((quality,rr,direction,setup,zone,target_zone,stop,target))
    if not accepted:
        return wait('HTF_CONFLICT_OR_RR_BELOW_1_40')
    # Ambiguous simultaneous opposing signals must not be executed.
    if len({x[2] for x in accepted})>1:
        return wait('CONFLICTING_SNR_DIRECTIONS')
    score,rr,direction,setup,zone,target_zone,stop,target = max(accepted,key=lambda x:(x[0],x[1]))
    out.update({'signal':direction,'state':'READY','reason':'Confirmed H1 zone with closed M5 '+setup+'; opposing observed H1 target',
                'confidence':score,'score':score,'setup':setup,'zone':zone,'target_zone':target_zone,
                'entry':round(entry,5),'stop_loss':round(stop,5),'take_profit':[round(target,5)],
                'risk_reward':round(rr,4),
                'checks':{'h1_pivot_touches':zone['touches']>=2,'h4_h1_bias':True,
                          'm5_closed_confirmation':True,'entry_fresh':True,'rr_min_1_40':True},
                'evidence':{'candle_time':last['time'],'atr_m5':round(atr5,5),'atr_h1':round(atr1,5),
                            'bias_h1':b1,'bias_h4':b4,'observed_target':True,'score_is_win_probability':False}})
    return out
