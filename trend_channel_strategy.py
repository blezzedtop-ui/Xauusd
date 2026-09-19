"""SignalX Trend Channel Engine.

Source scope: the six trend-focused books supplied after the ICT set:
1) Trendline Savdo Strategiyasi — Sirlarni Tekshirish
2) Trend chiziqlari: ularni savdoda qanday foydalanish kerak?
3) Trend savdo qilish strategiyasi
4) Trend kanallari
5) Parabolic SAR
6) M&W Trendline Trading Strategy

This module is deliberately deterministic. AI is a separate validator in main.py.
No market levels are invented: every level is derived from supplied OHLC candles.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import math


def f(c: dict[str, Any], k: str) -> float:
    return float(c[k])


def atr(candles: list[dict[str, Any]], n: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    trs: list[float] = []
    start = max(1, len(candles) - n)
    for i in range(start, len(candles)):
        c, p = candles[i], candles[i - 1]
        trs.append(max(
            f(c, "high") - f(c, "low"),
            abs(f(c, "high") - f(p, "close")),
            abs(f(c, "low") - f(p, "close")),
        ))
    return sum(trs) / max(1, len(trs))


def swings(candles: list[dict[str, Any]], left: int = 2, right: int = 2) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    for i in range(left, len(candles) - right):
        hi = f(candles[i], "high")
        lo = f(candles[i], "low")
        if hi >= max(f(candles[j], "high") for j in range(i-left, i+right+1)):
            highs.append((i, hi))
        if lo <= min(f(candles[j], "low") for j in range(i-left, i+right+1)):
            lows.append((i, lo))
    return highs, lows


def line_value(p1: tuple[int, float], p2: tuple[int, float], idx: int) -> float:
    if p2[0] == p1[0]:
        return p2[1]
    return p1[1] + ((p2[1] - p1[1]) / (p2[0] - p1[0])) * (idx - p1[0])


def _range(candles: list[dict[str, Any]]) -> float:
    if not candles:
        return 0.0
    return max(f(c, "high") for c in candles) - min(f(c, "low") for c in candles)


def _slope_angle(p1: tuple[int, float], p2: tuple[int, float], scale: float) -> float:
    dx = max(1, abs(p2[0] - p1[0]))
    dy = abs(p2[1] - p1[1])
    return math.degrees(math.atan2(dy / dx, max(scale, 1e-9)))


def _bullish_reversal(c: dict[str, Any], prev: dict[str, Any] | None) -> bool:
    o, h, l, cl = f(c, "open"), f(c, "high"), f(c, "low"), f(c, "close")
    body = abs(cl - o); rng = max(h - l, 1e-9)
    lower = min(o, cl) - l
    engulf = bool(prev) and cl > o and f(prev, "close") < f(prev, "open") and cl >= f(prev, "open") and o <= f(prev, "close")
    pin = lower >= max(body * 1.5, rng * 0.45) and cl >= o
    return engulf or pin or (cl > o and body / rng >= 0.6)


def _bearish_reversal(c: dict[str, Any], prev: dict[str, Any] | None) -> bool:
    o, h, l, cl = f(c, "open"), f(c, "high"), f(c, "low"), f(c, "close")
    body = abs(cl - o); rng = max(h - l, 1e-9)
    upper = h - max(o, cl)
    engulf = bool(prev) and cl < o and f(prev, "close") > f(prev, "open") and cl <= f(prev, "open") and o >= f(prev, "close")
    pin = upper >= max(body * 1.5, rng * 0.45) and cl <= o
    return engulf or pin or (cl < o and body / rng >= 0.6)


def _ma(candles: list[dict[str, Any]], n: int) -> float | None:
    if len(candles) < n:
        return None
    return sum(f(c, "close") for c in candles[-n:]) / n


def parabolic_sar(candles: list[dict[str, Any]], step: float = 0.02, maximum: float = 0.20) -> dict[str, Any]:
    if len(candles) < 5:
        return {"available": False, "signal": "WAIT", "value": None, "trend": "NEUTRAL"}
    highs = [f(c, "high") for c in candles]
    lows = [f(c, "low") for c in candles]
    bull = True
    sar = lows[0]
    ep = highs[0]
    af = step
    prev_sar = sar
    for i in range(1, len(candles)):
        sar = prev_sar + af * (ep - prev_sar)
        if bull:
            sar = min(sar, lows[i-1], lows[i-2] if i >= 2 else lows[i-1])
            if lows[i] < sar:
                bull = False
                sar = ep
                ep = lows[i]
                af = step
            elif highs[i] > ep:
                ep = highs[i]
                af = min(maximum, af + step)
        else:
            sar = max(sar, highs[i-1], highs[i-2] if i >= 2 else highs[i-1])
            if highs[i] > sar:
                bull = True
                sar = ep
                ep = highs[i]
                af = step
            elif lows[i] < ep:
                ep = lows[i]
                af = min(maximum, af + step)
        prev_sar = sar
    price = f(candles[-1], "close")
    return {"available": True, "value": round(sar, 5), "trend": "BULLISH" if bull else "BEARISH",
            "signal": "BUY" if price > sar else "SELL" if price < sar else "WAIT", "step": step, "maximum": maximum}


def analyze_trend_channel(candles: list[dict[str, Any]], higher_frames: dict[str, list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    """Deterministic six-book trend/channel model. Returns no AI fields."""
    higher_frames = higher_frames or {}
    if len(candles) < 60:
        return {"signal": "WAIT", "raw_direction": "WAIT", "confidence": 0, "state": "INSUFFICIENT_DATA",
                "reason": "Trend Channel Engine uchun yetarli candle mavjud emas.", "checks": {}, "entry": None,
                "stop_loss": None, "take_profit": [], "risk_reward": 0, "channel": {}, "trendline": {},
                "trend": "NEUTRAL", "trend_strength": "UNKNOWN", "parabolic_sar": {"available": False}}

    closed = candles[:-1] if len(candles) > 1 else candles
    price = f(closed[-1], "close")
    a = max(atr(closed), price * 0.0002)
    highs, lows = swings(closed, 2, 2)
    if len(highs) < 2 or len(lows) < 2:
        return {"signal":"WAIT","raw_direction":"WAIT","confidence":0,"state":"WAIT_SWINGS",
                "reason":"Aniq swing high/low yetarli emas.","checks":{"swings":False},"entry":None,"stop_loss":None,
                "take_profit":[],"risk_reward":0,"channel":{},"trendline":{},"trend":"NEUTRAL",
                "trend_strength":"UNKNOWN","parabolic_sar":parabolic_sar(closed)}

    # Prefer the most recent pair that preserves a coherent trend structure.
    last_lows = lows[-4:]
    last_highs = highs[-4:]
    bull_struct = last_lows[-1][1] > last_lows[-2][1] and last_highs[-1][1] > last_highs[-2][1]
    bear_struct = last_lows[-1][1] < last_lows[-2][1] and last_highs[-1][1] < last_highs[-2][1]
    trend = "BULLISH" if bull_struct else "BEARISH" if bear_struct else ("BULLISH" if _ma(closed, 20) and price > _ma(closed, 20) else "BEARISH" if _ma(closed,20) and price < _ma(closed,20) else "NEUTRAL")

    primary_points = last_lows if trend == "BULLISH" else last_highs
    p1, p2 = primary_points[-2], primary_points[-1]
    primary = "support" if trend == "BULLISH" else "resistance"
    line_at = line_value(p1, p2, len(closed)-1)

    # Parallel boundary is calibrated from the most recent opposite swing farthest from the primary line.
    opposite_points = last_highs if trend == "BULLISH" else last_lows
    if trend == "BULLISH":
        distances = [(p, p[1] - line_value(p1,p2,p[0])) for p in opposite_points[-5:]]
        positive = [item for item in distances if item[1] > 0]
        offset = max(positive, key=lambda item: item[1])[1] if positive else 0.0
        channel_boundary = line_at + offset
    else:
        distances = [(p, p[1] - line_value(p1,p2,p[0])) for p in opposite_points[-5:]]
        negative = [item for item in distances if item[1] < 0]
        offset = min(negative, key=lambda item: item[1])[1] if negative else 0.0
        channel_boundary = line_at + offset
    width = abs(offset)
    if width < a * 0.6:
        # Use the recent range as a conservative channel width if the swing geometry is too tight.
        width = max(a * 1.2, _range(closed[-30:]) * 0.25)
        channel_boundary = line_at + (width if trend == "BULLISH" else -width)

    lower = min(line_at, channel_boundary)
    upper = max(line_at, channel_boundary)
    support_line = line_at if trend == "BULLISH" else channel_boundary
    resistance_line = channel_boundary if trend == "BULLISH" else line_at

    # Count touches within 0.35 ATR; source books emphasise repeated touches and significant swings.
    touch_tol = max(a * 0.35, price * 0.00025)
    support_touches = 0; resistance_touches = 0
    for i in range(max(0, len(closed)-120), len(closed)):
        lv = support_line + ((p2[1]-p1[1])/(p2[0]-p1[0]) if p2[0]!=p1[0] else 0) * (i-(len(closed)-1))
        rv = resistance_line + ((p2[1]-p1[1])/(p2[0]-p1[0]) if p2[0]!=p1[0] else 0) * (i-(len(closed)-1))
        if abs(f(closed[i],"low")-lv) <= touch_tol or abs(f(closed[i],"close")-lv) <= touch_tol:
            support_touches += 1
        if abs(f(closed[i],"high")-rv) <= touch_tol or abs(f(closed[i],"close")-rv) <= touch_tol:
            resistance_touches += 1
    touches = support_touches + resistance_touches

    last = closed[-1]; prev = closed[-2]
    near_support = abs(price - support_line) <= max(a * 0.55, width * 0.10)
    near_resistance = abs(price - resistance_line) <= max(a * 0.55, width * 0.10)
    breakout_up = f(last,"close") > resistance_line + touch_tol
    breakout_down = f(last,"close") < support_line - touch_tol
    pa_buy = _bullish_reversal(last, prev)
    pa_sell = _bearish_reversal(last, prev)

    # Retest proxy: latest candle is back within the former boundary after a prior breakout.
    retest_up = False; retest_down = False
    if len(closed) >= 4:
        prior2 = closed[-3]
        retest_up = f(prior2,"close") > resistance_line and f(last,"low") <= resistance_line + touch_tol and price >= resistance_line
        retest_down = f(prior2,"close") < support_line and f(last,"high") >= support_line - touch_tol and price <= support_line

    # Higher timeframe agreement follows the supplied six-book MTF hierarchy.
    mtf_rows = []
    for tf in ("1day","4h","1h"):
        c = higher_frames.get(tf) or []
        if len(c) >= 30:
            hh, ll = swings(c,2,2)
            if len(hh)>=2 and len(ll)>=2:
                d = "BULLISH" if hh[-1][1] > hh[-2][1] and ll[-1][1] > ll[-2][1] else "BEARISH" if hh[-1][1] < hh[-2][1] and ll[-1][1] < ll[-2][1] else "NEUTRAL"
            else:
                m20=_ma(c,20); cp=f(c[-1],"close"); d="BULLISH" if m20 and cp>m20 else "BEARISH" if m20 and cp<m20 else "NEUTRAL"
            mtf_rows.append({"timeframe":tf,"trend":d})
    mtf_direction = "BULLISH" if sum(1 for x in mtf_rows if x["trend"]=="BULLISH") > sum(1 for x in mtf_rows if x["trend"]=="BEARISH") else "BEARISH" if sum(1 for x in mtf_rows if x["trend"]=="BEARISH") > sum(1 for x in mtf_rows if x["trend"]=="BULLISH") else "NEUTRAL"
    mtf_match = mtf_direction in {"NEUTRAL", trend}

    ma20 = _ma(closed,20); ma50 = _ma(closed,50); ma200 = _ma(closed,200)
    ma_alignment = ((trend=="BULLISH" and ((ma20 is None or price>=ma20) and (ma50 is None or price>=ma50) and (ma200 is None or price>=ma200))) or
                    (trend=="BEARISH" and ((ma20 is None or price<=ma20) and (ma50 is None or price<=ma50) and (ma200 is None or price<=ma200))) or trend=="NEUTRAL")
    psar = parabolic_sar(closed)
    psar_match = psar.get("trend") in {trend, "NEUTRAL"}

    # Book-style trend strength: more touches + gentler slope = stronger trendline.
    base_scale = max(price * 0.001, a)
    slope_angle = _slope_angle(p1,p2,base_scale)
    if touches >= 6 and slope_angle < 40:
        strength = "STRONG"
    elif touches >= 4 and slope_angle < 55:
        strength = "NORMAL"
    elif touches >= 3:
        strength = "WEAK"
    else:
        strength = "FORMING"

    bounce_signal = "BUY" if trend=="BULLISH" and near_support and pa_buy else "SELL" if trend=="BEARISH" and near_resistance and pa_sell else "WAIT"
    breakout_signal = "BUY" if breakout_up and retest_up else "SELL" if breakout_down and retest_down else "WAIT"
    raw_direction = breakout_signal if breakout_signal!="WAIT" else bounce_signal

    checks = {
        "trend_structure": trend in {"BULLISH","BEARISH"},
        "two_point_trendline": True,
        "three_touch_or_more": touches >= 3,
        "channel_defined": width > 0,
        "price_at_boundary": near_support or near_resistance,
        "price_action_confirmation": pa_buy if raw_direction=="BUY" else pa_sell if raw_direction=="SELL" else False,
        "breakout_retest": retest_up if raw_direction=="BUY" and breakout_up else retest_down if raw_direction=="SELL" and breakout_down else False,
        "mtf_alignment": mtf_match,
        "ma_alignment": ma_alignment,
        "parabolic_sar_alignment": psar_match,
        "h1_h4_quality": True,
    }

    score = 0
    score += 15 if checks["trend_structure"] else 0
    score += 10 if checks["two_point_trendline"] else 0
    score += 10 if checks["three_touch_or_more"] else 0
    score += 15 if checks["channel_defined"] else 0
    score += 15 if checks["price_at_boundary"] else 0
    score += 10 if checks["price_action_confirmation"] else 0
    score += 10 if checks["breakout_retest"] else 0
    score += 5 if checks["mtf_alignment"] else 0
    score += 5 if checks["ma_alignment"] else 0
    score += 5 if checks["parabolic_sar_alignment"] else 0

    entry = stop = None; tps: list[float] = []; rr = 0.0
    if raw_direction == "BUY":
        entry = price
        stop = support_line - a * 0.65
        target = resistance_line if resistance_line > entry else entry + max(width, a*2)
        if target > entry:
            rr = (target-entry) / max(entry-stop, a*0.6)
            tps = [target]
    elif raw_direction == "SELL":
        entry = price
        stop = resistance_line + a * 0.65
        target = support_line if support_line < entry else entry - max(width, a*2)
        if target < entry:
            rr = (entry-target) / max(stop-entry, a*0.6)
            tps = [target]

    # The channel book gives bounce/breakout + retest, while the risk books use RR as a hard implementation gate.
    final_raw = raw_direction if raw_direction in {"BUY","SELL"} and score >= 75 and rr >= 1.50 else "WAIT"
    reasons = []
    if final_raw == "BUY": reasons.append("bullish channel support + price-action confirmation")
    elif final_raw == "SELL": reasons.append("bearish channel resistance + price-action confirmation")
    if touches >= 3: reasons.append(f"{touches} channel/trendline touch reactions")
    if breakout_signal != "WAIT": reasons.append("channel breakout + retest")
    if not mtf_match: reasons.append("MTF conflict")
    if rr < 1.50: reasons.append(f"RR {rr:.2f} below 1.50")

    return {
        "signal": final_raw, "raw_direction": raw_direction, "confidence": int(min(100, score)),
        "score": int(min(100, score)), "state": "READY_FOR_AI" if final_raw in {"BUY","SELL"} else "WAIT",
        "trend": trend, "trend_strength": strength, "touches": touches, "slope_angle": round(slope_angle,2),
        "channel": {"support": round(support_line,5), "resistance": round(resistance_line,5), "width": round(width,5),
                     "near_support": near_support, "near_resistance": near_resistance, "breakout_up": breakout_up,
                     "breakout_down": breakout_down, "retest_up": retest_up, "retest_down": retest_down},
        "trendline": {"primary": primary, "p1": p1, "p2": p2, "value": round(line_at,5), "slope_angle": round(slope_angle,2)},
        "structure": {"bullish": bull_struct, "bearish": bear_struct, "last_high": round(last_highs[-1][1],5), "last_low": round(last_lows[-1][1],5)},
        "price_action": {"bullish_reversal": pa_buy, "bearish_reversal": pa_sell},
        "moving_averages": {"ma20": round(ma20,5) if ma20 is not None else None, "ma50": round(ma50,5) if ma50 is not None else None,
                             "ma200": round(ma200,5) if ma200 is not None else None, "alignment": ma_alignment},
        "parabolic_sar": psar,
        "mtf": {"rows": mtf_rows, "direction": mtf_direction, "match": mtf_match},
        "checks": checks,
        "entry": round(entry,5) if entry is not None and final_raw in {"BUY","SELL"} else None,
        "stop_loss": round(stop,5) if stop is not None and final_raw in {"BUY","SELL"} else None,
        "take_profit": [round(x,5) for x in tps] if final_raw in {"BUY","SELL"} else [],
        "risk_reward": round(rr,2),
        "reason": "; ".join(dict.fromkeys(reasons)) or "Trend channel setup incomplete.",
        "source_scope": ["Trendline construction", "3-touch validation", "Breakout/Retest", "Channel boundaries", "HH/HL-LH/LL", "200MA/20MA/50MA", "Price action reversal", "MTF", "Parabolic SAR", "Risk/RR"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
