"""Nine isolated, closed-candle strategies. Pure calculations; no orders or I/O.

These are testable rule sets, not backtested performance claims. All times are
UTC bar-open seconds. BUY/SELL requires every rule of that module, not votes
from other modules. AI can only veto the resulting immutable candidate.
"""
from __future__ import annotations

import math
from statistics import mean, pstdev

VERSION = "SX9-1"
MIN_RR = 1.0
INTERVALS = {"5min": 300, "15min": 900, "30min": 1800, "1h": 3600, "4h": 14400}
MODULES = {
    "ict-ai-pro": dict(source="ICT AI Pro", section="ictSection", interval="5min", name="Liquidity sweep → MSS → FVG retest", rules="M30 bias; M5 sweep; displacement va MSS; yangi FVG retest; yopilgan sham tasdig‘i."),
    "snr": dict(source="SNR", section="msaiStrategySection", interval="5min", name="Confirmed S/R rejection", rules="Kamida 2 tasdiqlangan swingdan zona; rejection sham; HTFga qarshi emas; qarshi zona oldida TP."),
    "ai-analysis": dict(source="AI Analysis", section="smartAnalysisSection", interval="15min", name="Regime-adaptive AI validation", rules="Efficiency ratio bilan rejim; trendda Donchian breakout; rangeda Bollinger re-entry; alohida AI veto."),
    "trend": dict(source="Trend", section="trendChannelSection", interval="15min", name="HTF-aligned EMA pullback", rules="EMA20/50 va HTF bir yo‘nalishda; EMA20 pullback; yopilgan rejection sham; strukturaviy SL."),
    "trendline": dict(source="Trend liniya", section="trendLineSection", interval="5min", name="Confirmed trendline third touch", rules="2 tasdiqlangan swingdan chiziq; 3-touch va rejection; buzilmagan chiziq; HTF filtri."),
    "technical": dict(source="Technical Analysis", section="analysisSection", interval="15min", name="Volatility squeeze breakout", rules="Bollinger siqilishi; banddan yopilish; RSI va MACD momentum; HTF qarama-qarshi emas."),
    "classic": dict(source="Classic Trade", section="classicSection", interval="15min", name="Double top/bottom neckline retest", rules="2 tasdiqlangan pivot; neckline breakout; keyingi shamda retest; measured-move chegarasi."),
    "ob": dict(source="OB Trade", section="smcSection", interval="5min", name="Fresh displacement order-block retest", rules="Strukturani buzgan displacement; undan oldingi qarshi sham OB; birinchi retest; rejection va HTF."),
    "fibonacci": dict(source="Fibonacci Trade", section="fibonacciSection", interval="15min", name="Confirmed swing golden-zone continuation", rules="Tasdiqlangan impuls; 50–61.8% qaytish; rejection; HTF mos; oldingi swingdan uzoq TP majburlanmaydi."),
}
SOURCES = frozenset(m["source"] for m in MODULES.values())
SOURCE_IDS = {m["source"].casefold(): k for k, m in MODULES.items()}


def module_id(source):
    raw = str(source or "").strip()
    return raw if raw in MODULES else SOURCE_IDS.get(raw.casefold())


def reward_risk(direction, entry, stop, targets):
    """Validate every level, with TP1 as the actual execution target. No RR cap."""
    try:
        e, s = float(entry), float(stop)
        tps = [float(x) for x in targets]
        if not tps or not all(math.isfinite(x) and x > 0 for x in [e, s, *tps]):
            return None
        sign = 1 if direction == "BUY" else -1 if direction == "SELL" else 0
        risk = sign * (e - s)
        if not sign or risk <= 0 or any(sign * (t - e) <= 0 for t in tps):
            return None
        if any(sign * (b - a) < 0 for a, b in zip(tps, tps[1:])):
            return None
        value = sign * (tps[0] - e) / risk
        return value if math.isfinite(value) else None
    except (TypeError, ValueError, OverflowError):
        return None


def closed_candles(candles, seconds, now, minimum=80):
    """Reject malformed/future/out-of-order feeds; never synthesize candles."""
    result, last_time = [], -1
    for raw in candles:
        try:
            c = {k: float(raw[k]) for k in ("time", "open", "high", "low", "close")}
        except (KeyError, TypeError, ValueError):
            raise ValueError("INVALID_CANDLES") from None
        if not all(math.isfinite(v) for v in c.values()):
            raise ValueError("INVALID_CANDLES")
        if c["time"] <= last_time or c["time"] > now + 5 or c["time"] % seconds:
            raise ValueError("INVALID_CANDLE_TIME")
        if min(c[k] for k in ("open", "high", "low", "close")) <= 0 or not (
            c["low"] <= min(c["open"], c["close"]) <= max(c["open"], c["close"]) <= c["high"]
        ):
            raise ValueError("INVALID_OHLC")
        last_time = c["time"]
        c["time"] = int(c["time"])
        if c["time"] + seconds <= now:
            result.append(c)
    if len(result) < minimum:
        raise ValueError("INSUFFICIENT_CLOSED_CANDLES")
    # One-bar grace accommodates provider publication delay, not delayed feeds.
    if now - (result[-1]["time"] + seconds) > seconds + 30:
        raise ValueError("STALE_CANDLES")
    if any(b["time"] - a["time"] != seconds for a, b in zip(result[-8:], result[-7:])):
        raise ValueError("RECENT_DATA_GAP")
    return result


def ema(values, length):
    out = float(values[0])
    for v in values[1:]:
        out += 2 / (length + 1) * (v - out)
    return out


def atr(candles):
    return mean(max(c["high"] - c["low"], abs(c["high"] - p["close"]), abs(c["low"] - p["close"])) for p, c in zip(candles[-15:-1], candles[-14:]))


def pivots(candles, side, width=2):
    # Right-hand confirmation already exists in these closed candles.
    key = "low" if side == "BUY" else "high"
    test = min if side == "BUY" else max
    out = []
    for i in range(width, len(candles) - width):
        vals = [c[key] for c in candles[i-width:i+width+1]]
        if candles[i][key] == test(vals) and vals.count(candles[i][key]) == 1:
            out.append((i, candles[i][key]))
    return out


def bias(candles):
    v = [c["close"] for c in candles]
    fast, slow = ema(v, 20), ema(v, 50)
    return "BUY" if v[-1] > fast > slow else "SELL" if v[-1] < fast < slow else "NEUTRAL"


def rejection(c, direction):
    size = c["high"] - c["low"]
    return size > 0 and (c["close"] > c["open"] and c["close"] >= c["low"] + .6 * size if direction == "BUY" else c["close"] < c["open"] and c["close"] <= c["high"] - .6 * size)


def wait(mid, reason, **extra):
    return dict(module_id=mid, source=MODULES[mid]["source"], strategy=MODULES[mid]["name"], contract_version=VERSION,
                signal="WAIT", entry=None, stop_loss=None, take_profit=[], risk_reward=None,
                state=reason, reason=reason, evidence={}, **extra)


def _setup(mid, direction, candles, stop, rr, evidence, target_ceiling=None):
    e, a = candles[-1]["close"], atr(candles)
    sign = 1 if direction == "BUY" else -1
    risk = sign * (e - stop)
    if not .25 * a <= risk <= 4 * a:
        return wait(mid, "STRUCTURAL_RISK_OUT_OF_RANGE", checks=evidence)
    target = e + sign * risk * rr
    if target_ceiling is not None and sign * (target_ceiling - target) < -.00001:
        return wait(mid, "TARGET_BLOCKED_BY_STRUCTURE", checks=evidence)
    # Round only once. Reject a rounded RR < 1 rather than mislabelling it.
    e, stop = (round(v, 5) for v in (e, stop))
    target = e + sign * abs(e-stop) * rr
    if not math.isfinite(target):
        return wait(mid,"TARGET_NOT_FINITE",checks=evidence)
    target = (math.ceil(target*100000-1e-7) if sign>0 else math.floor(target*100000+1e-7))/100000
    actual = reward_risk(direction, e, stop, [target])
    if actual is None or actual < MIN_RR - 1e-8:
        return wait(mid, "RR_BELOW_1", checks=evidence)
    return dict(module_id=mid, source=MODULES[mid]["source"], strategy=MODULES[mid]["name"], contract_version=VERSION,
                signal=direction, entry=e, stop_loss=stop, take_profit=[target], risk_reward=actual,
                requested_rr=rr, order_type="MARKET", confidence=85, state="AWAITING_AI",
                reason=MODULES[mid]["rules"], evidence=evidence, atr=a,
                candle_time=str(candles[-1]["time"]))


def analyze(mid, candles, higher, rr=2.0):
    """Input must be validated closed candles; each branch is an isolated strategy."""
    if mid not in MODULES:
        raise ValueError("UNKNOWN_MODULE")
    if not math.isfinite(rr) or rr < MIN_RR:
        raise ValueError("RR_MUST_BE_FINITE_AND_AT_LEAST_1")
    if len(candles) < 80 or len(higher) < 80:
        return wait(mid, "INSUFFICIENT_CLOSED_CANDLES")
    cs, hs = candles, higher
    c, prev, a = cs[-1], cs[-2], atr(cs)
    v = [x["close"] for x in cs]
    ht, local = bias(hs), bias(cs)
    evidence = {"htf_bias": ht, "local_bias": local, "atr": round(a, 5), "closed_candle": c["time"]}
    if a <= 0 or c["high"] - c["low"] > 3.5 * a:
        return wait(mid, "VOLATILITY_GUARD", checks=evidence)
    for direction in ("BUY", "SELL"):
        sign = 1 if direction == "BUY" else -1
        if ht not in (direction, "NEUTRAL"):
            continue
        touches = lambda lo, hi: c["low"] <= hi and c["high"] >= lo
        stop = min(x["low"] for x in cs[-5:]) - .15*a if direction == "BUY" else max(x["high"] for x in cs[-5:]) + .15*a
        ceiling = None
        checks = dict(evidence)
        passed = False
        if mid == "snr":
            ps = pivots(cs[:-1], direction)
            clusters = [(p, [q for q in ps if abs(q[1]-p[1]) <= .3*a]) for p in ps[-16:]]
            zones = [(p, qs) for p, qs in clusters if len(qs) >= 2 and max(q[0] for q in qs)-min(q[0] for q in qs) >= 3]
            for p, qs in reversed(zones):
                level = mean(q[1] for q in qs)
                if touches(level-.25*a, level+.25*a) and sign*(c["close"]-level) > 0 and rejection(c,direction):
                    stop = min(c["low"], level-.3*a)-.1*a if direction=="BUY" else max(c["high"],level+.3*a)+.1*a
                    opposing = [x[1] for x in pivots(cs[:-1], "SELL" if direction=="BUY" else "BUY") if sign*(x[1]-c["close"]) > .25*a]
                    ceiling = min(opposing) if direction=="BUY" and opposing else max(opposing) if opposing else None
                    checks.update(zone=level,touches=len(qs),rejection=True)
                    passed = True
                    break
        elif mid == "trend":
            e20, e50 = ema(v,20), ema(v,50)
            passed = ht==direction and local==direction and sign*(e20-ema(v[:-3],20)) > .05*a and touches(e20-.3*a,e20+.3*a) and rejection(c,direction)
            checks.update(ema20=e20,ema50=e50,pullback=touches(e20-.3*a,e20+.3*a))
        elif mid == "trendline":
            ps = pivots(cs[:-1], direction)
            if len(ps)>=2:
                (i,p),(j,q)=ps[-2:]
                slope=(q-p)/(j-i)
                line=q+slope*(len(cs)-1-j)
                intact=all(sign*(cs[k]["close"]-(q+slope*(k-j)))>=-.25*a for k in range(j+1,len(cs)-1))
                passed=sign*slope>0 and j-i>=3 and intact and touches(line-.2*a,line+.2*a) and sign*(c["close"]-line)>0 and rejection(c,direction)
                stop=min(c["low"],line-.3*a)-.1*a if direction=="BUY" else max(c["high"],line+.3*a)+.1*a
                checks.update(anchors=[[cs[i]["time"],p],[cs[j]["time"],q]],projected_line=line,intact=intact,third_touch=passed)
        elif mid in {"technical", "ai-analysis"}:
            avg, sd = mean(v[-21:-1]), pstdev(v[-21:-1])
            upper, lower=avg+2*sd,avg-2*sd
            moves=[b-a0 for a0,b in zip(v[-15:-1],v[-14:])]
            gains=sum(max(0,x) for x in moves); losses=sum(max(0,-x) for x in moves)
            rsi=100*gains/(gains+losses) if gains+losses else 50
            macds=[ema(v[:i],12)-ema(v[:i],26) for i in range(len(v)-35,len(v)+1)]
            hist=macds[-1]-ema(macds,9)
            if mid=="technical":
                squeeze=sd < .8*pstdev(v[-61:-1])
                passed=squeeze and sign*(c["close"]-(upper if direction=="BUY" else lower))>0 and sign*hist>0 and (55<=rsi<=78 if direction=="BUY" else 22<=rsi<=45)
                checks.update(squeeze=squeeze,rsi=rsi,macd_histogram=hist,upper_band=upper,lower_band=lower)
            else:
                travel=sum(abs(b-a0) for a0,b in zip(v[-21:-1],v[-20:]))
                efficiency=abs(v[-1]-v[-21])/travel if travel else 0
                boundary=max(x["high"] for x in cs[-21:-1]) if direction=="BUY" else min(x["low"] for x in cs[-21:-1])
                trend=efficiency>=.45 and ht==direction and sign*(c["close"]-boundary)>0
                reentry=(prev["close"]<lower<c["close"]<avg if direction=="BUY" else prev["close"]>upper>c["close"]>avg)
                ranging=efficiency<=.25 and ht=="NEUTRAL" and reentry and rejection(c,direction)
                passed=trend or ranging
                if ranging: ceiling=avg
                checks.update(efficiency_ratio=efficiency,regime="TREND" if efficiency>=.45 else "RANGE" if efficiency<=.25 else "TRANSITION",donchian=boundary,reentry=reentry)
        elif mid == "classic":
            ps=pivots(cs[:-2],direction)
            if len(ps)>=2:
                (i,p),(j,q)=ps[-2:]
                neck=max(x["high"] for x in cs[i:j+1]) if direction=="BUY" else min(x["low"] for x in cs[i:j+1])
                crossed=any(sign*(cs[k-1]["close"]-neck)<=0<sign*(cs[k]["close"]-neck) for k in range(j+2,len(cs)-1))
                passed=abs(q-p)<=.5*a and j-i>=5 and crossed and sign*(prev["close"]-neck)>0 and touches(neck-.2*a,neck+.2*a) and sign*(c["close"]-neck)>0 and rejection(c,direction)
                stop=c["low"]-.25*a if direction=="BUY" else c["high"]+.25*a
                ceiling=neck+sign*abs(neck-mean([p,q]))
                checks.update(pattern="DOUBLE_BOTTOM" if direction=="BUY" else "DOUBLE_TOP",neckline=neck,breakout=crossed,retest=passed,measured_target=ceiling)
        elif mid == "fibonacci":
            lows, highs=pivots(cs[:-1],"BUY"),pivots(cs[:-1],"SELL")
            ends=highs if direction=="BUY" else lows
            starts=lows if direction=="BUY" else highs
            if ends:
                j,end=ends[-1]
                starts=[p for p in starts if p[0]<j]
                if starts:
                    i,start=starts[-1]; impulse=sign*(end-start)
                    lo,hi=sorted([end-sign*impulse*.618,end-sign*impulse*.5])
                    passed=ht==direction and impulse>=2*a and touches(lo,hi) and rejection(c,direction) and sign*(c["close"]-start)>0 and all(sign*(x["close"]-start)>0 for x in cs[j+1:])
                    stop=start-sign*.15*a; ceiling=end
                    checks.update(anchor_start=[cs[i]["time"],start],anchor_end=[cs[j]["time"],end],golden_zone=[lo,hi],rejection=passed)
        elif mid in {"ict-ai-pro", "ob"}:
            # A recent displacement must break pre-existing structure; only the
            # first later retest is allowed. Future pivots cannot change anchors.
            for j in range(len(cs)-3,max(20,len(cs)-11),-1):
                d=cs[j]
                level=max(x["high"] for x in cs[j-5:j]) if direction=="BUY" else min(x["low"] for x in cs[j-5:j])
                displacement=sign*(d["close"]-d["open"])>=.8*a and sign*(d["close"]-level)>0
                if not displacement or ht!=direction:
                    continue
                if mid=="ob":
                    origins=[k for k in range(j-4,j) if sign*(cs[k]["close"]-cs[k]["open"])<0]
                    if not origins: continue
                    k=origins[-1]; lo,hi=cs[k]["low"],cs[k]["high"]; end=j
                    stop=lo-.15*a if direction=="BUY" else hi+.15*a
                    checks.update(order_block=[lo,hi],origin_time=cs[k]["time"],bos_level=level)
                else:
                    k=j-1; sweep=cs[k]
                    external=min(x["low"] for x in cs[k-20:k]) if direction=="BUY" else max(x["high"] for x in cs[k-20:k])
                    swept=(sweep["low"]<external<sweep["close"] if direction=="BUY" else sweep["high"]>external>sweep["close"])
                    left,right=cs[j-1],cs[j+1]
                    lo,hi=(left["high"],right["low"]) if direction=="BUY" else (right["high"],left["low"])
                    if not swept or hi<=lo: continue
                    end=j+1; stop=sweep["low"]-.15*a if direction=="BUY" else sweep["high"]+.15*a
                    checks.update(external_liquidity=external,sweep_time=sweep["time"],mss_level=level,fvg=[lo,hi])
                fresh=not any(x["low"]<=hi and x["high"]>=lo for x in cs[end+1:-1])
                passed=fresh and touches(lo,hi) and rejection(c,direction) and (c["close"]>hi if direction=="BUY" else c["close"]<lo)
                checks.update(displacement_time=d["time"],fresh=fresh,retest=passed)
                if passed: break
        if passed:
            return _setup(mid,direction,cs,stop,rr,checks,ceiling)
    return wait(mid,"SETUP_NOT_CONFIRMED",checks=evidence)
