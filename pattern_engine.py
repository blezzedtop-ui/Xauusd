from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import math
from statistics import mean, pstdev


EPS = 1e-9


def _f(x: Any) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1.0 - k)
    return e


def _atr(candles: list[dict[str, Any]], period: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    trs = []
    for i in range(max(1, len(candles) - period), len(candles)):
        c = candles[i]
        p = candles[i - 1]
        hi, lo, pc = _f(c.get("high")), _f(c.get("low")), _f(p.get("close"))
        trs.append(max(hi - lo, abs(hi - pc), abs(lo - pc)))
    return mean(trs) if trs else max(_f(candles[-1].get("high")) - _f(candles[-1].get("low")), 0.0001)


def _swing_points(candles: list[dict[str, Any]], left: int = 2, right: int = 2) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    if len(candles) < left + right + 5:
        return highs, lows
    for i in range(left, len(candles) - right):
        hi = _f(candles[i].get("high")); lo = _f(candles[i].get("low"))
        left_h = [_f(candles[j].get("high")) for j in range(i - left, i)]
        right_h = [_f(candles[j].get("high")) for j in range(i + 1, i + right + 1)]
        left_l = [_f(candles[j].get("low")) for j in range(i - left, i)]
        right_l = [_f(candles[j].get("low")) for j in range(i + 1, i + right + 1)]
        if hi >= max(left_h + right_h):
            highs.append((i, hi))
        if lo <= min(left_l + right_l):
            lows.append((i, lo))
    return highs, lows


def _linear_slope(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    xmean = (n - 1) / 2
    ymean = mean(values)
    den = sum((i - xmean) ** 2 for i in range(n)) or 1.0
    return sum((i - xmean) * (y - ymean) for i, y in enumerate(values)) / den


def _avg_body(candles: list[dict[str, Any]]) -> float:
    vals = [abs(_f(c.get("close")) - _f(c.get("open"))) for c in candles[-20:]]
    return mean(vals) if vals else 0.0


def _candle_confirmation(candles: list[dict[str, Any]], direction: str) -> tuple[bool, str]:
    if len(candles) < 3:
        return False, "not enough candles"
    c = candles[-2]  # completed candle
    o, cl = _f(c.get("open")), _f(c.get("close"))
    body = abs(cl - o)
    rng = max(_f(c.get("high")) - _f(c.get("low")), EPS)
    strong = body / rng >= 0.5
    if direction == "BUY":
        return cl > o and strong, "bullish confirmation candle" if cl > o and strong else "weak bullish candle"
    return cl < o and strong, "bearish confirmation candle" if cl < o and strong else "weak bearish candle"


def _mtf_alignment(direction: str, candles_by_tf: dict[str, list[dict[str, Any]]], current_tf: str) -> dict[str, Any]:
    order = ["4h", "1h", "30min", "15min", "5min"]
    usable = [tf for tf in order if tf in candles_by_tf and len(candles_by_tf.get(tf) or []) >= 40]
    votes: dict[str, str] = {}
    for tf in usable:
        c = candles_by_tf[tf]
        closes = [_f(x.get("close")) for x in c]
        e20 = _ema(closes[-80:], 20)
        e50 = _ema(closes[-120:], 50)
        price = closes[-1]
        if e20 > e50 and price > e20:
            votes[tf] = "BULLISH"
        elif e20 < e50 and price < e20:
            votes[tf] = "BEARISH"
        else:
            votes[tf] = "NEUTRAL"
    target = "BULLISH" if direction == "BUY" else "BEARISH"
    matches = sum(1 for tf, v in votes.items() if v == target and tf != current_tf)
    considered = sum(1 for tf in votes if tf != current_tf)
    score = int(round(100 * matches / max(considered, 1))) if considered else 50
    return {"votes": votes, "matches": matches, "considered": considered, "alignment_score": score,
            "state": "ALIGNED" if matches >= max(2, math.ceil(considered * 0.6)) else "MIXED"}


def _breakout(candles: list[dict[str, Any]], level: float, direction: str, atr_value: float) -> dict[str, Any]:
    if level <= 0 or len(candles) < 3:
        return {"confirmed": False, "level": level, "distance_atr": 0.0, "retest": False}
    completed = candles[-2]
    close = _f(completed.get("close"))
    prev = candles[-3]
    prev_close = _f(prev.get("close"))
    buffer = max(atr_value * 0.15, 0.0001)
    if direction == "BUY":
        confirmed = close > level + buffer and prev_close <= level + buffer
    else:
        confirmed = close < level - buffer and prev_close >= level - buffer
    retest = False
    if len(candles) >= 2:
        recent = candles[-2]
        if direction == "BUY":
            retest = _f(recent.get("low")) <= level + atr_value * 0.35 and close > level
        else:
            retest = _f(recent.get("high")) >= level - atr_value * 0.35 and close < level
    dist = abs(close - level) / max(atr_value, EPS)
    false_break = (direction == "BUY" and close <= level) or (direction == "SELL" and close >= level)
    return {"confirmed": bool(confirmed), "level": round(level, 5), "distance_atr": round(dist, 2),
            "retest": bool(retest), "false_breakout_risk": "LOW" if dist >= 0.25 and not false_break else "HIGH"}


def _recent_range(candles: list[dict[str, Any]], count: int = 20) -> tuple[float, float]:
    cs = candles[-count:]
    return (max(_f(c.get("high")) for c in cs), min(_f(c.get("low")) for c in cs))


def _pattern_double(candles: list[dict[str, Any]], direction: str, atr_value: float) -> dict[str, Any] | None:
    highs, lows = _swing_points(candles[:-2], 2, 2)
    if direction == "BUY" and len(lows) >= 2:
        a, b = lows[-2], lows[-1]
        if b[0] - a[0] < 4:
            return None
        similar = abs(a[1] - b[1]) <= max(0.55 * atr_value, 0.002)
        between = [_f(candles[i].get("high")) for i in range(a[0], b[0] + 1)]
        neckline = max(between) if between else 0.0
        br = _breakout(candles, neckline, "BUY", atr_value)
        if similar and neckline > max(a[1], b[1]) and br["confirmed"]:
            height = neckline - min(a[1], b[1])
            return {"name":"Double Bottom","category":"REVERSAL","direction":"BUY","invalidation":min(a[1], b[1]),"neckline":neckline,"height":height,"anchors":{"low1":a,"low2":b},"breakout":br}
    if direction == "SELL" and len(highs) >= 2:
        a, b = highs[-2], highs[-1]
        if b[0] - a[0] < 4:
            return None
        similar = abs(a[1] - b[1]) <= max(0.55 * atr_value, 0.002)
        between = [_f(candles[i].get("low")) for i in range(a[0], b[0] + 1)]
        neckline = min(between) if between else 0.0
        br = _breakout(candles, neckline, "SELL", atr_value)
        if similar and neckline < min(a[1], b[1]) and br["confirmed"]:
            height = max(a[1], b[1]) - neckline
            return {"name":"Double Top","category":"REVERSAL","direction":"SELL","invalidation":max(a[1], b[1]),"neckline":neckline,"height":height,"anchors":{"high1":a,"high2":b},"breakout":br}
    return None


def _pattern_triple(candles: list[dict[str, Any]], direction: str, atr_value: float) -> dict[str, Any] | None:
    highs, lows = _swing_points(candles[:-2], 2, 2)
    if direction == "BUY" and len(lows) >= 3:
        pts = lows[-3:]
        sim = max(pts, key=lambda x:x[1])[1] - min(pts, key=lambda x:x[1])[1] <= max(0.8*atr_value, 0.003)
        between_highs = [_f(candles[i].get("high")) for i in range(pts[0][0], pts[-1][0]+1)]
        neckline = max(between_highs) if between_highs else 0
        br = _breakout(candles, neckline, "BUY", atr_value)
        if sim and br["confirmed"]:
            h = neckline - min(p[1] for p in pts)
            return {"name":"Triple Bottom","category":"REVERSAL","direction":"BUY","invalidation":min(p[1] for p in pts),"neckline":neckline,"height":h,"anchors":{"lows":pts},"breakout":br}
    if direction == "SELL" and len(highs) >= 3:
        pts = highs[-3:]
        sim = max(p[1] for p in pts) - min(p[1] for p in pts) <= max(0.8*atr_value, 0.003)
        between_lows = [_f(candles[i].get("low")) for i in range(pts[0][0], pts[-1][0]+1)]
        neckline = min(between_lows) if between_lows else 0
        br = _breakout(candles, neckline, "SELL", atr_value)
        if sim and br["confirmed"]:
            h = max(p[1] for p in pts) - neckline
            return {"name":"Triple Top","category":"REVERSAL","direction":"SELL","invalidation":max(p[1] for p in pts),"neckline":neckline,"height":h,"anchors":{"highs":pts},"breakout":br}
    return None


def _pattern_hs(candles: list[dict[str, Any]], inverse: bool, atr_value: float) -> dict[str, Any] | None:
    highs, lows = _swing_points(candles[:-2], 2, 2)
    if inverse:
        if len(lows) < 3 or len(highs) < 2: return None
        pts = lows[-3:]; shoulders_ok = abs(pts[0][1] - pts[2][1]) <= max(0.75*atr_value, 0.003)
        head_ok = pts[1][1] < min(pts[0][1], pts[2][1]) - max(0.5*atr_value,0.001)
        trough_peaks = [p for p in highs if pts[0][0] < p[0] < pts[2][0]]
        if not trough_peaks: return None
        neckline = mean(p[1] for p in trough_peaks[-2:])
        br = _breakout(candles, neckline, "BUY", atr_value)
        if shoulders_ok and head_ok and br["confirmed"]:
            return {"name":"Inverse Head & Shoulders","category":"REVERSAL","direction":"BUY","invalidation":pts[1][1],"neckline":neckline,"height":neckline-pts[1][1],"anchors":{"lows":pts},"breakout":br}
    else:
        if len(highs) < 3 or len(lows) < 2: return None
        pts = highs[-3:]; shoulders_ok = abs(pts[0][1] - pts[2][1]) <= max(0.75*atr_value, 0.003)
        head_ok = pts[1][1] > max(pts[0][1], pts[2][1]) + max(0.5*atr_value,0.001)
        neck_pts = [p for p in lows if pts[0][0] < p[0] < pts[2][0]]
        if not neck_pts: return None
        neckline = mean(p[1] for p in neck_pts[-2:])
        br = _breakout(candles, neckline, "SELL", atr_value)
        if shoulders_ok and head_ok and br["confirmed"]:
            return {"name":"Head & Shoulders","category":"REVERSAL","direction":"SELL","invalidation":pts[1][1],"neckline":neckline,"height":pts[1][1]-neckline,"anchors":{"highs":pts},"breakout":br}
    return None


def _pattern_channel(candles: list[dict[str, Any]], atr_value: float) -> list[dict[str, Any]]:
    cs = candles[:-2]
    if len(cs) < 30: return []
    window = cs[-24:]
    highs = [_f(c.get("high")) for c in window]
    lows = [_f(c.get("low")) for c in window]
    hi_s = _linear_slope(highs); lo_s = _linear_slope(lows)
    early = window[:12]; late = window[12:]
    er = mean(_f(c.get("high"))-_f(c.get("low")) for c in early)
    lr = mean(_f(c.get("high"))-_f(c.get("low")) for c in late)
    rng_hi, rng_lo = max(highs), min(lows)
    out=[]
    if er > 2.0*atr_value and lr < 0.75*er:
        base_hi=max(_f(c.get("high")) for c in window[:-2]); base_lo=min(_f(c.get("low")) for c in window[:-2])
        # Impulse direction from first half to second half.
        impulse = _f(window[10].get("close")) - _f(window[0].get("open"))
        if impulse > 1.5*atr_value:
            if lo_s < 0 and hi_s < 0 and abs(hi_s-lo_s) < 0.2*atr_value:
                out.append({"name":"Bullish Flag","category":"CONTINUATION","direction":"BUY","invalidation":rng_lo,"neckline":base_hi,"height":er,"anchors":{},"breakout":None})
            if hi_s < 0 and lo_s < 0 and abs(hi_s-lo_s) >= 0.2*atr_value:
                out.append({"name":"Bullish Pennant","category":"CONTINUATION","direction":"BUY","invalidation":rng_lo,"neckline":base_hi,"height":er,"anchors":{},"breakout":None})
        elif impulse < -1.5*atr_value:
            if hi_s > 0 and lo_s > 0 and abs(hi_s-lo_s) < 0.2*atr_value:
                out.append({"name":"Bearish Flag","category":"CONTINUATION","direction":"SELL","invalidation":rng_hi,"neckline":base_lo,"height":er,"anchors":{},"breakout":None})
            if hi_s > 0 and lo_s > 0 and abs(hi_s-lo_s) >= 0.2*atr_value:
                out.append({"name":"Bearish Pennant","category":"CONTINUATION","direction":"SELL","invalidation":rng_hi,"neckline":base_lo,"height":er,"anchors":{},"breakout":None})
    return out


def _pattern_triangle(candles: list[dict[str, Any]], atr_value: float) -> list[dict[str, Any]]:
    cs = candles[:-2]
    if len(cs) < 25: return []
    w=cs[-24:]
    hs=[_f(c.get("high")) for c in w]; ls=[_f(c.get("low")) for c in w]
    hi_s=_linear_slope(hs); lo_s=_linear_slope(ls)
    hi_flat=abs(hi_s) <= atr_value*0.05; lo_flat=abs(lo_s) <= atr_value*0.05
    out=[]
    # Determine breakout level from recent boundary.
    if hi_flat and lo_s > atr_value*0.05:
        level=max(hs)
        br=_breakout(candles,level,"BUY",atr_value)
        if br["confirmed"]: out.append({"name":"Ascending Triangle","category":"BREAKOUT","direction":"BUY","invalidation":min(ls),"neckline":level,"height":level-min(ls),"anchors":{},"breakout":br})
    if lo_flat and hi_s < -atr_value*0.05:
        level=min(ls)
        br=_breakout(candles,level,"SELL",atr_value)
        if br["confirmed"]: out.append({"name":"Descending Triangle","category":"BREAKOUT","direction":"SELL","invalidation":max(hs),"neckline":level,"height":max(hs)-level,"anchors":{},"breakout":br})
    if hi_s < -atr_value*0.04 and lo_s > atr_value*0.04:
        hi_level=max(hs[-6:]); lo_level=min(ls[-6:])
        up=_breakout(candles,hi_level,"BUY",atr_value); dn=_breakout(candles,lo_level,"SELL",atr_value)
        if up["confirmed"]:
            out.append({"name":"Symmetrical Triangle","category":"BILATERAL","direction":"BUY","invalidation":lo_level,"neckline":hi_level,"height":hi_level-lo_level,"anchors":{},"breakout":up})
        elif dn["confirmed"]:
            out.append({"name":"Symmetrical Triangle","category":"BILATERAL","direction":"SELL","invalidation":hi_level,"neckline":lo_level,"height":hi_level-lo_level,"anchors":{},"breakout":dn})
    return out


def _pattern_wedge(candles: list[dict[str, Any]], atr_value: float) -> list[dict[str, Any]]:
    cs=candles[:-2]
    if len(cs)<25:return []
    w=cs[-24:]
    hs=[_f(c.get("high")) for c in w]; ls=[_f(c.get("low")) for c in w]
    hi_s=_linear_slope(hs); lo_s=_linear_slope(ls)
    out=[]
    if hi_s > 0 and lo_s > 0 and lo_s > hi_s*1.15:
        level=min(ls[-5:]); br=_breakout(candles,level,"SELL",atr_value)
        if br["confirmed"]: out.append({"name":"Rising Wedge","category":"REVERSAL","direction":"SELL","invalidation":max(hs),"neckline":level,"height":max(hs)-level,"anchors":{},"breakout":br})
    if hi_s < 0 and lo_s < 0 and abs(lo_s) > abs(hi_s)*1.15:
        level=max(hs[-5:]); br=_breakout(candles,level,"BUY",atr_value)
        if br["confirmed"]: out.append({"name":"Falling Wedge","category":"REVERSAL","direction":"BUY","invalidation":min(ls),"neckline":level,"height":level-min(ls),"anchors":{},"breakout":br})
    return out


def _pattern_rectangle(candles: list[dict[str, Any]], atr_value: float) -> list[dict[str, Any]]:
    cs=candles[:-2]
    if len(cs)<25:return []
    w=cs[-24:]
    hs=[_f(c.get("high")) for c in w]; ls=[_f(c.get("low")) for c in w]
    width=max(hs)-min(ls)
    if width < atr_value*1.5:return []
    flat_hi=(max(hs)-min(hs)) <= atr_value*0.8
    flat_lo=(max(ls)-min(ls)) <= atr_value*0.8
    if not(flat_hi and flat_lo):return []
    top=max(hs); bot=min(ls)
    out=[]
    up=_breakout(candles,top,"BUY",atr_value); dn=_breakout(candles,bot,"SELL",atr_value)
    if up["confirmed"]:
        out.append({"name":"Bullish Rectangle","category":"CONTINUATION","direction":"BUY","invalidation":bot,"neckline":top,"height":width,"anchors":{},"breakout":up})
    elif dn["confirmed"]:
        out.append({"name":"Bearish Rectangle","category":"CONTINUATION","direction":"SELL","invalidation":top,"neckline":bot,"height":width,"anchors":{},"breakout":dn})
    return out


def _pattern_rounding(candles: list[dict[str, Any]], inverse: bool, atr_value: float) -> dict[str, Any] | None:
    cs=candles[:-2]
    if len(cs)<40:return None
    w=cs[-36:]
    closes=[_f(c.get("close")) for c in w]
    a=_linear_slope(closes[:12]); b=_linear_slope(closes[12:24]); c=_linear_slope(closes[24:])
    current=closes[-1]
    base=min(closes) if not inverse else max(closes)
    if not inverse:
        good=a < -atr_value*0.03 and b <= 0 and c > atr_value*0.03
        level=max(closes[:12])
        br=_breakout(candles,level,"BUY",atr_value)
        if good and br["confirmed"]:
            return {"name":"Rounding Bottom","category":"REVERSAL","direction":"BUY","invalidation":base,"neckline":level,"height":level-base,"anchors":{},"breakout":br}
    else:
        good=a > atr_value*0.03 and b >= 0 and c < -atr_value*0.03
        level=min(closes[:12])
        br=_breakout(candles,level,"SELL",atr_value)
        if good and br["confirmed"]:
            return {"name":"Rounding Top","category":"REVERSAL","direction":"SELL","invalidation":base,"neckline":level,"height":base-level,"anchors":{},"breakout":br}
    return None


def _pattern_cup_handle(candles: list[dict[str, Any]], atr_value: float) -> dict[str, Any] | None:
    cs=candles[:-2]
    if len(cs)<50:return None
    w=cs[-45:]
    closes=[_f(c.get("close")) for c in w]
    left=max(closes[:10]); mid=min(closes[15:30]); right=max(closes[30:38]); handle=min(closes[-8:])
    if abs(left-right) > max(1.2*atr_value, left*0.0015): return None
    depth=left-mid
    if depth < 2.0*atr_value: return None
    level=max(closes[:15]); br=_breakout(candles,level,"BUY",atr_value)
    if br["confirmed"]:
        return {"name":"Cup & Handle","category":"CONTINUATION","direction":"BUY","invalidation":handle,"neckline":level,"height":depth,"anchors":{},"breakout":br}
    return None


def _pattern_diamond(candles: list[dict[str, Any]], direction: str, atr_value: float) -> dict[str, Any] | None:
    cs=candles[:-2]
    if len(cs)<36:return None
    w=cs[-30:]
    ranges=[_f(c.get("high"))-_f(c.get("low")) for c in w]
    first=mean(ranges[:10]); mid=mean(ranges[10:20]); last=mean(ranges[20:])
    if not(first < mid*0.85 and last < mid*0.85):
        return None
    hi=max(_f(c.get("high")) for c in w); lo=min(_f(c.get("low")) for c in w)
    level=lo if direction=="SELL" else hi
    br=_breakout(candles,level,direction,atr_value)
    if not br["confirmed"]: return None
    return {"name":"Diamond Bottom" if direction=="BUY" else "Diamond Top","category":"REVERSAL","direction":direction,
            "invalidation":lo if direction=="BUY" else hi,"neckline":level,"height":hi-lo,"anchors":{},"breakout":br}


def _detect_candidates(candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    a=max(_atr(candles), _f(candles[-1].get("close"))*0.0001)
    cands=[]
    # Explicit reversal patterns by direction.
    for direction in ("BUY","SELL"):
        for fn in (
            lambda: _pattern_double(candles,direction,a),
            lambda: _pattern_triple(candles,direction,a),
            lambda: _pattern_hs(candles, direction=="BUY", a),
            lambda: _pattern_diamond(candles,direction,a),
        ):
            try:
                x=fn()
                if x:cands.append(x)
            except Exception:
                pass
    for fn in (
        lambda: _pattern_rounding(candles,False,a), lambda: _pattern_rounding(candles,True,a),
        lambda: _pattern_cup_handle(candles,a),
    ):
        try:
            x=fn()
            if x:cands.append(x)
        except Exception:
            pass
    for fn in (
        lambda: _pattern_channel(candles,a), lambda: _pattern_triangle(candles,a),
        lambda: _pattern_wedge(candles,a), lambda: _pattern_rectangle(candles,a),
    ):
        try:cands.extend([x for x in fn() if x])
        except Exception:pass
    # Remove duplicate pattern names/directions, keeping the first fresh detection.
    seen=set(); out=[]
    for x in cands:
        k=(x.get("name"),x.get("direction"))
        if k in seen: continue
        seen.add(k); out.append(x)
    return out


def _pattern_scores(pattern: dict[str, Any], candles: list[dict[str, Any]], candles_by_tf: dict[str, list[dict[str, Any]]], interval: str) -> dict[str, Any]:
    direction=pattern["direction"]
    atr_value=max(_atr(candles), _f(candles[-1].get("close"))*0.0001)
    current=_f(candles[-1].get("close"))
    mtf=_mtf_alignment(direction,candles_by_tf,interval)
    candle_ok,candle_reason=_candle_confirmation(candles,direction)
    body=_avg_body(candles)
    br=pattern.get("breakout") or {}
    breakout_score=20 if br.get("confirmed") else 0
    if br.get("retest"): breakout_score += 3
    breakout_score=min(20,breakout_score)
    structure_score=35
    if pattern.get("category")=="BILATERAL": structure_score=32
    if pattern.get("height",0) < atr_value*1.2: structure_score-=8
    structure_score=max(0,structure_score)
    mtf_score=round(20*mtf.get("alignment_score",50)/100)
    # Lightweight S/R context: being near a recent extreme improves location quality.
    high,low=_recent_range(candles,30)
    near_sr=min(abs(current-high),abs(current-low)) <= atr_value*1.0
    sr_score=10 if near_sr else 5
    candle_score=10 if candle_ok else 4
    # Session score is deterministic, based on UTC market liquidity windows.
    import datetime as _dt
    hour=_dt.datetime.now(_dt.timezone.utc).hour
    session_score=5 if 7 <= hour <= 16 else 3
    total=min(100, int(structure_score+breakout_score+mtf_score+sr_score+candle_score+session_score))
    return {"pattern_structure":structure_score,"breakout_confirmation":breakout_score,"mtf":mtf_score,
            "snr_context":sr_score,"candle_confirmation":candle_score,"session_condition":session_score,
            "deterministic_score":total,"mtf_alignment":mtf,"candle_ok":candle_ok,"candle_reason":candle_reason,
            "atr":round(atr_value,5),"current":round(current,5),"avg_body":round(body,5)}


def _levels(pattern: dict[str, Any], candles: list[dict[str, Any]]) -> dict[str, Any]:
    current=_f(candles[-1].get("close")); a=max(_atr(candles), current*0.0001)
    direction=pattern["direction"]
    invalid=_f(pattern.get("invalidation")); neck=_f(pattern.get("neckline")); height=max(_f(pattern.get("height")), a)
    buffer=max(a*0.18,current*0.00025)
    if direction=="BUY":
        sl=invalid-buffer if invalid>0 else current-a
        target=max(neck+height, current+height*0.8)
        tp2=max(target+height*0.6, current+height*1.35)
    else:
        sl=invalid+buffer if invalid>0 else current+a
        target=min(neck-height, current-height*0.8)
        tp2=min(target-height*0.6, current-height*1.35)
    return {"entry":round(current,5),"stop_loss":round(sl,5),"take_profit":[round(target,5),round(tp2,5)],
            "invalidation":round(invalid,5),"neckline":round(neck,5),"height":round(height,5)}


def detect_patterns(candles: list[dict[str, Any]], candles_by_tf: dict[str, list[dict[str, Any]]] | None = None, interval: str = "5min") -> dict[str, Any]:
    candles_by_tf = candles_by_tf or {interval: candles}
    candidates=_detect_candidates(candles)
    ranked=[]
    for p in candidates:
        scores=_pattern_scores(p,candles,candles_by_tf,interval)
        levels=_levels(p,candles)
        # Pattern trigger requires a confirmed breakout; bilateral patterns never guess early direction.
        valid = bool((p.get("breakout") or {}).get("confirmed"))
        final_score=scores["deterministic_score"]
        ptype=p.get("category")
        # More stringent raw detector quality for reversal and continuation patterns.
        threshold=70 if ptype in {"REVERSAL","CONTINUATION"} else 68
        state="READY_FOR_AI" if valid and final_score>=threshold else "DETECTED_WAIT"
        ranked.append({**p,**scores,**levels,"pattern_valid":valid,"state":state,"raw_score":final_score,"threshold":threshold})
    ranked.sort(key=lambda x:(x.get("state") == "READY_FOR_AI", x.get("raw_score",0)), reverse=True)
    best=ranked[0] if ranked else None
    result={"interval":interval,"detected":len(ranked),"patterns":ranked,"best":best,
            "signal":"WAIT","raw_direction":"WAIT","confidence":0,"score":0,"state":"DETECTED_WAIT",
            "pattern":None,"pattern_type":None,
            "entry":None,"stop_loss":None,"take_profit":[],"risk_reward":None,
            "ai_gate":{"required":True,"passed":False,"minimum_confidence":85,"minimum_agreement":70,"strict":True},
            "reason":"No confirmed pattern breakout."}
    if best and best.get("state")=="READY_FOR_AI":
        entry=float(best["entry"]); sl=float(best["stop_loss"]); tp1=float((best.get("take_profit") or [0])[0])
        risk=abs(entry-sl); reward=abs(tp1-entry)
        rr=round(reward/risk,2) if risk>0 else None
        result.update({"signal":best["direction"],"raw_direction":best["direction"],"confidence":best["raw_score"],
                       "score":best["raw_score"],"state":"READY_FOR_AI","pattern":best["name"],
                       "pattern_type":best["category"],"entry":best["entry"],"stop_loss":best["stop_loss"],
                       "take_profit":best["take_profit"],"risk_reward":rr,
                       "reason":f'{best["name"]} {best["category"]} confirmed by breakout; AI validation pending.',
                       "pattern_details":best})
    return result
