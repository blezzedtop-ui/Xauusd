"""SignalX ICT-only closed-candle setup scanner. No broker orders or AI calls here.

A liquidity sweep must precede directional displacement/MSS, then a 3-bar FVG
must be retested on the most recently CLOSED M5 candle. Price targets must be
observed historical liquidity, not fabricated RR levels. All failures -> WAIT.
"""
from __future__ import annotations
import math
import time
from datetime import datetime, timezone

TF_SECONDS = {"4h":14400,"1h":3600,"30min":1800,"15min":900,"5min":300}
MIN_RR = 1.40

def closed_bars(bars, timeframe, now=None):
    now = time.time() if now is None else float(now)
    seconds = TF_SECONDS[timeframe]
    selected = {}
    for raw in bars or []:
        try:
            c = {k: float(raw[k]) for k in ("open","high","low","close")}
            t = int(float(raw["time"]))
            if t <= 0 or not all(math.isfinite(x) and x > 0 for x in c.values()):
                continue
            if c["high"] < max(c["open"], c["close"]) or c["low"] > min(c["open"], c["close"]):
                continue
            if t + seconds <= now - 1: # never use a partially formed bar
                selected[t] = {"time":t, **c}
        except (ValueError, KeyError, TypeError, OverflowError):
            continue
    return [selected[t] for t in sorted(selected)]

def _ema(values, period):
    if len(values) < period: return None
    v = sum(values[:period]) / period
    k = 2 / (period+1)
    for x in values[period:]:v += (x-v)*k
    return v

def _atr(bars, period=14):
    if len(bars) < period + 1:return 0.
    values = [max(bars[i]["high"] - bars[i]["low"], abs(bars[i]["high"] - bars[i-1]["close"]), abs(bars[i]["low"] - bars[i-1]["close"])) for i in range(-period,0)]
    return sum(values)/len(values)

def _bias(bars):
    closes=[b["close"] for b in bars]
    e20,e50=_ema(closes,20),_ema(closes,50)
    if e20 is None or e50 is None:return "NEUTRAL"
    return "BULLISH" if closes[-1] > e20 > e50 else "BEARISH" if closes[-1] < e20 < e50 else "NEUTRAL"

def analyze_ict(closed_by_tf, *, live_price=None, now=None, min_rr=MIN_RR):
    now = time.time() if now is None else float(now)
    m5 = closed_by_tf.get("5min", [])
    result = {"signal":"WAIT", "state":"WAIT", "reason":"INSUFFICIENT_CLOSED_CANDLES", "confidence":0,
              "score":0, "entry":None,"stop_loss":None,"take_profit":[],"risk_reward":None,
              "bias":"NEUTRAL", "checks":[], "liquidity":{"type":"NONE","level":None,"extreme":None},
              "premium_discount":{"zone":"—","equilibrium":None},
              "m30":{"fvg":{"type":"NONE"},"order_block":{"type":"NONE"},"ema20":None,"ema50":None},
              "m5":{"mss":False,"mss_level":None,"displacement":False,"displacement_atr":0,"fvg":{"type":"NONE"}},
              "draw_on_liquidity":"NONE","candle_time":str(m5[-1]["time"]) if m5 else "", "model":"ICT Sweep → MSS → FVG retest"}
    def wait(reason):
        result["reason"] = reason
        return result
    if any(len(closed_by_tf.get(tf,[])) < minimum for tf,minimum in (("4h",55),("1h",65),("30min",65),("15min",35),("5min",90))):
        return wait("INSUFFICIENT_CLOSED_CANDLES")
    if now - (m5[-1]["time"]+300) > 360: return wait("STALE_M5_CANDLE")
    if any(now - (closed_by_tf[tf][-1]["time"]+TF_SECONDS[tf]) > TF_SECONDS[tf]*2.5 for tf in ("4h","1h","30min","15min")):
        return wait("STALE_HIGHER_TIMEFRAME")
    h4,h1,m30,m15 = (closed_by_tf[tf] for tf in ("4h","1h","30min","15min"))
    b4,b1,b30,b15 = (_bias(x) for x in (h4,h1,m30,m15))
    result["bias"] = b1
    pd_low=min(c["low"] for c in m30[-60:]); pd_high=max(c["high"] for c in m30[-60:])
    eq=(pd_low+pd_high)/2
    result["premium_discount"]={"zone":"DISCOUNT" if m30[-1]["close"]<eq else "PREMIUM", "equilibrium":round(eq,4),"high":pd_high,"low":pd_low}
    result["m30"]["ema20"]=_ema([x["close"] for x in m30],20)
    result["m30"]["ema50"]=_ema([x["close"] for x in m30],50)
    a5=_atr(m5)
    if a5<=0:return wait("INVALID_ATR")
    found=None
    # Search at most 18 closed bars back, but require an MSS and later FVG retest.
    for i in range(len(m5)-4, max(28,len(m5)-19), -1):
        preceding=m5[max(0,i-18):i]
        bar=m5[i]
        pre_low=min(c["low"] for c in preceding); pre_high=max(c["high"] for c in preceding)
        direction = "BUY" if bar["low"]<pre_low and bar["close"]>pre_low else "SELL" if bar["high"]>pre_high and bar["close"]<pre_high else None
        if not direction:continue
        expected="BULLISH" if direction=="BUY" else "BEARISH"
        if b4==("BEARISH" if direction=="BUY" else "BULLISH") or b1!=expected or b30!=expected or b15==("BEARISH" if direction=="BUY" else "BULLISH"):
            continue
        if direction=="BUY" and bar["close"]>eq or direction=="SELL" and bar["close"]<eq:
            continue
        # Structure break of an earlier short-range high/low, on a directional body.
        level = max(c["high"] for c in m5[max(0,i-12):i]) if direction=="BUY" else min(c["low"] for c in m5[max(0,i-12):i])
        for j in range(i+1, min(len(m5)-2,i+9)):
            move=m5[j]; body=abs(move["close"]-move["open"])
            mss=(move["close"]>level and move["close"]>move["open"]) if direction=="BUY" else (move["close"]<level and move["close"]<move["open"])
            if not mss or body < a5*.80:continue
            for k in range(j, len(m5)-1):
                if k < 2:continue
                first, third=m5[k-2],m5[k]
                fvg_low = first["high"] if direction=="BUY" else third["high"]
                fvg_high = third["low"] if direction=="BUY" else first["low"]
                if fvg_high <= fvg_low:continue
                # Displacement must belong to the 3-candle imbalance pattern.
                if j not in (k-1,k):continue
                retest=m5[-1]
                if retest["time"] <= third["time"]:continue
                if not (retest["low"]<=fvg_high and retest["high"]>=fvg_low):continue
                if direction=="BUY" and retest["close"]< (fvg_low+fvg_high)/2:continue
                if direction=="SELL" and retest["close"]> (fvg_low+fvg_high)/2:continue
                found=(direction,bar,pre_low if direction=="BUY" else pre_high,level,body/a5,{"type":expected,"low":round(fvg_low,4),"high":round(fvg_high,4),"index":k},i,j)
                break
            if found:break
        if found:break
    if not found:return wait("SWEEP_MSS_FVG_RETEST_NOT_CONFIRMED")
    direction,sweep,level,mss_level,disp_ratio,fvg,si,mi=found
    # Entry is the latest available tradable price, not the midpoint of a stale FVG.
    entry=float(live_price) if live_price is not None else m5[-1]["close"]
    if not math.isfinite(entry) or entry<=0:return wait("INVALID_LIVE_PRICE")
    if abs(entry-m5[-1]["close"]) > max(a5*.35,entry*.00012):return wait("ENTRY_DEVIATION_TOO_LARGE")
    extreme=sweep["low"] if direction=="BUY" else sweep["high"]
    stop=min(extreme,fvg["low"])-a5*.12 if direction=="BUY" else max(extreme,fvg["high"])+a5*.12
    risk=entry-stop if direction=="BUY" else stop-entry
    if risk<=0 or risk>max(a5*5,entry*.004):return wait("INVALID_STOP_GEOMETRY")
    # Actual preceding liquidity targets: never manufacture a 1.4R target.
    candles=m30[-85:]+h1[-75:]
    highs=[c["high"] for c in candles]; lows=[c["low"] for c in candles]
    if direction=="BUY": targets=sorted(set(x for x in highs if entry+min_rr*risk < x <= entry+6*risk))
    else: targets=sorted(set((x for x in lows if entry-6*risk <= x < entry-min_rr*risk)),reverse=True)
    if not targets:return wait("NO_VALID_LIQUIDITY_TARGET_RR_1_40")
    tp1=targets[0]; tp2=next((v for v in targets[1:] if abs(v-tp1)>risk*.35),None)
    rr=(tp1-entry)/risk if direction=="BUY" else (entry-tp1)/risk
    if rr < min_rr-1e-9:return wait("RR_BELOW_MINIMUM")
    result.update({"signal":direction,"state":"READY","confidence":90,"score":90,
                   "entry":round(entry,4),"stop_loss":round(stop,4),"take_profit":[round(v,4) for v in (tp1,tp2) if v is not None],"risk_reward":round(rr,3),
                   "reason":"Closed candles: liquidity sweep → displacement/MSS → FVG retest; HTF aligned",
                   "current_price":round(entry,4),"liquidity":{"type":"SSL_SWEEP" if direction=="BUY" else "BSL_SWEEP","level":round(level,4),"extreme":round(extreme,4)},
                   "draw_on_liquidity":"SSL_SWEEP" if direction=="BUY" else "BSL_SWEEP",
                   "m5":{"mss":True,"mss_level":round(mss_level,4),"displacement":True,"displacement_atr":round(disp_ratio,2),"fvg":fvg,"atr":round(a5,4)},
                   "checks":[{"name":x,"status":"PASS","points":0} for x in ("HTF Bias","Liquidity Sweep","Premium/Discount","M5 MSS","M5 Displacement","M5 FVG Retest","Risk & RR")],
                   "evidence":{"sweep_time":sweep["time"],"mss_time":m5[mi]["time"],"fvg_time":m5[fvg["index"]]["time"],"retest_time":m5[-1]["time"],"htf":{"H4":b4,"H1":b1,"M30":b30,"M15":b15}}})
    return result
