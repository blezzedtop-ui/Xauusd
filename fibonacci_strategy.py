from __future__ import annotations

from math import isfinite
from statistics import median
from typing import Any


RETRACEMENTS = (0.236, 0.382, 0.50, 0.618, 0.786)
EXTENSIONS = (1.272, 1.618, 2.618, 4.236)
MUSANG_LEVELS = {
    "alert_entry": (0.12, 0.236),
    "premature_entry": (0.382, 0.50),
    "pullback": (0.786,),
    "breakout": (0.88,),
    "premature_tp": (1.272, 1.314),
    "tp1": (1.618,),
    "tp1_extended": (1.786, 1.88),
    "tp2": (2.618,),
    "tp2_extended": (2.786, 2.88),
    "cycle": (4.23, 4.786, 4.88),
}


def _f(c: dict[str, Any], key: str, default: float | None = None) -> float | None:
    try:
        v = float(c.get(key))
    except (TypeError, ValueError):
        return default
    return v if isfinite(v) else default


def _atr(candles: list[dict[str, Any]], period: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    rows = candles[-(period + 1):]
    trs: list[float] = []
    prev_close = _f(rows[0], "close")
    for c in rows[1:]:
        h, l, cl = _f(c, "high"), _f(c, "low"), _f(c, "close")
        if h is None or l is None or cl is None:
            continue
        tr = h - l
        if prev_close is not None:
            tr = max(tr, abs(h - prev_close), abs(l - prev_close))
        trs.append(tr)
        prev_close = cl
    return sum(trs) / len(trs) if trs else 0.0


def _ranges(candles: list[dict[str, Any]]) -> list[float]:
    out: list[float] = []
    for c in candles:
        h, l = _f(c, "high"), _f(c, "low")
        if h is not None and l is not None and h > l:
            out.append(h - l)
    return out


def _body(c: dict[str, Any]) -> float:
    o, cl = _f(c, "open"), _f(c, "close")
    return abs(cl - o) if o is not None and cl is not None else 0.0


def _swings(candles: list[dict[str, Any]], left: int = 2, right: int = 2) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    if len(candles) < left + right + 3:
        return highs, lows
    for i in range(left, len(candles) - right):
        hi = _f(candles[i], "high")
        lo = _f(candles[i], "low")
        if hi is not None:
            left_h = [_f(candles[j], "high") for j in range(i - left, i)]
            right_h = [_f(candles[j], "high") for j in range(i + 1, i + right + 1)]
            if all(v is not None and hi >= v for v in left_h + right_h):
                highs.append((i, hi))
        if lo is not None:
            left_l = [_f(candles[j], "low") for j in range(i - left, i)]
            right_l = [_f(candles[j], "low") for j in range(i + 1, i + right + 1)]
            if all(v is not None and lo <= v for v in left_l + right_l):
                lows.append((i, lo))
    return highs, lows


def _trend(highs: list[tuple[int, float]], lows: list[tuple[int, float]], candles: list[dict[str, Any]]) -> str:
    if len(highs) >= 2 and len(lows) >= 2:
        hh = highs[-1][1] > highs[-2][1]
        hl = lows[-1][1] > lows[-2][1]
        lh = highs[-1][1] < highs[-2][1]
        ll = lows[-1][1] < lows[-2][1]
        if hh and hl:
            return "BULLISH"
        if lh and ll:
            return "BEARISH"
    closes = [_f(c, "close") for c in candles[-20:]]
    closes = [x for x in closes if x is not None]
    if len(closes) >= 10:
        fast = sum(closes[-10:]) / 10
        slow = sum(closes) / len(closes)
        if fast > slow:
            return "BULLISH"
        if fast < slow:
            return "BEARISH"
    return "NEUTRAL"


def _fib_price(a: float, b: float, ratio: float, direction: str) -> float:
    # Retracement/projection coordinate between A/B. For bullish swing low->high,
    # retracement sits below B; for bearish high->low, retracement sits above B.
    if direction == "BULLISH":
        return b - (b - a) * ratio
    return b + (a - b) * ratio


def _extension_price(a: float, b: float, ratio: float, direction: str) -> float:
    if direction == "BULLISH":
        return a + (b - a) * ratio
    return a - (a - b) * ratio


def _near(price: float, level: float | None, tol: float) -> bool:
    return level is not None and abs(price - level) <= tol


def _pinbar(c: dict[str, Any], bullish: bool, ratio: float = 1.6) -> bool:
    o, h, l, cl = _f(c, "open"), _f(c, "high"), _f(c, "low"), _f(c, "close")
    if None in (o, h, l, cl):
        return False
    body = max(abs(cl - o), 1e-9)
    upper = max(0.0, h - max(o, cl))
    lower = max(0.0, min(o, cl) - l)
    rng = h - l
    if rng <= 0:
        return False
    if bullish:
        return lower >= body * ratio and lower >= upper * 1.15 and cl >= l + rng * 0.55
    return upper >= body * ratio and upper >= lower * 1.15 and cl <= h - rng * 0.55


def _crossed_level(prev_close: float, close: float, level: float, direction: str) -> bool:
    if direction == "BULLISH":
        return prev_close <= level < close
    return prev_close >= level > close


def _dominant_candle(candles: list[dict[str, Any]]) -> tuple[int, dict[str, Any]] | None:
    if len(candles) < 8:
        return None
    bodies = [_body(c) for c in candles[-45:]]
    base = median(bodies) if bodies else 0.0
    start = len(candles) - len(bodies)
    best: tuple[int, dict[str, Any]] | None = None
    for idx in range(start, len(candles) - 3):
        c = candles[idx]
        h, l = _f(c, "high"), _f(c, "low")
        bd = _body(c)
        if h is None or l is None or bd < max(base * 1.8, 0.0):
            continue
        children = candles[idx + 1:idx + 4]
        contained = 0
        for ch in children:
            chh, chl = _f(ch, "high"), _f(ch, "low")
            if chh is not None and chl is not None and chl >= l - (h-l)*0.10 and chh <= h + (h-l)*0.10:
                contained += 1
        if contained >= 2:
            if best is None or bd > _body(best[1]):
                best = (idx, c)
    return best


def _nearest_sr(highs: list[tuple[int, float]], lows: list[tuple[int, float]], price: float) -> tuple[str, float] | None:
    levels = [("RESISTANCE", v) for _, v in highs[-8:] if v > price] + [("SUPPORT", v) for _, v in lows[-8:] if v < price]
    return min(levels, key=lambda x: abs(x[1] - price), default=None)


def _mtf_direction(higher_frames: dict[str, list[dict[str, Any]]]) -> str:
    votes = []
    for tf in ("1day", "4h", "1h"):
        c = higher_frames.get(tf) or []
        if len(c) < 20:
            continue
        h, l = _swings(c)
        d = _trend(h, l, c)
        if d in {"BULLISH", "BEARISH"}:
            votes.append(d)
    if votes.count("BULLISH") > votes.count("BEARISH"):
        return "BULLISH"
    if votes.count("BEARISH") > votes.count("BULLISH"):
        return "BEARISH"
    return "NEUTRAL"


def analyze_fibonacci(candles: list[dict[str, Any]], higher_frames: dict[str, list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    higher_frames = higher_frames or {}
    if len(candles) < 60:
        return {"signal": "WAIT", "confidence": 0, "score": 0, "state": "INSUFFICIENT_DATA", "reason": "Fibonacci engine uchun yetarli candle yo‘q."}

    closed = candles[:-1] if len(candles) > 1 else candles
    price = _f(closed[-1], "close")
    if price is None:
        return {"signal": "WAIT", "confidence": 0, "score": 0, "state": "BAD_DATA", "reason": "Close narx mavjud emas."}

    atr = _atr(closed)
    ranges = _ranges(closed[-80:])
    median_range = median(ranges) if ranges else atr
    volatility_ratio = (atr / median_range) if median_range else 1.0
    high_volatility = volatility_ratio >= 1.9

    highs, lows = _swings(closed)
    trend = _trend(highs, lows, closed)
    if trend == "NEUTRAL":
        return {"signal": "WAIT", "confidence": 0, "score": 0, "state": "NO_CLEAR_TREND", "trend": trend,
                "reason": "Clear HH/HL yoki LH/LL structure aniqlanmadi."}

    # Primary A-B swing: a recent major swing followed by a correction.
    if trend == "BULLISH":
        candidates = [(i, v) for i, v in lows if any(h_i > i for h_i, _ in highs)]
        if not candidates or not highs:
            return {"signal": "WAIT", "confidence": 0, "score": 0, "state": "NO_SWING", "trend": trend,
                    "reason": "Bullish Fibonacci uchun valid swing aniqlanmadi."}
        a = candidates[-1]
        future_highs = [x for x in highs if x[0] > a[0]]
        b = future_highs[-1]
    else:
        candidates = [(i, v) for i, v in highs if any(l_i > i for l_i, _ in lows)]
        if not candidates or not lows:
            return {"signal": "WAIT", "confidence": 0, "score": 0, "state": "NO_SWING", "trend": trend,
                    "reason": "Bearish Fibonacci uchun valid swing aniqlanmadi."}
        a = candidates[-1]
        future_lows = [x for x in lows if x[0] > a[0]]
        b = future_lows[-1]

    ai, av = a
    bi, bv = b
    if bi <= ai or abs(bv-av) <= max(atr * 0.8, price * 0.0004):
        return {"signal": "WAIT", "confidence": 0, "score": 0, "state": "SWING_TOO_SMALL", "trend": trend,
                "reason": "Asosiy swing Fibonacci uchun yetarli emas."}

    fibs = {str(r): _fib_price(av, bv, r, trend) for r in RETRACEMENTS}
    exts = {str(r): _extension_price(av, bv, r, trend) for r in EXTENSIONS}
    tol = max(atr * 0.35, price * 0.00035)

    nearest_fib = min(fibs.items(), key=lambda kv: abs(price-kv[1]))
    fib_near = abs(price-nearest_fib[1]) <= tol
    fib_zone_ratio = float(nearest_fib[0])

    # Multiple relevant swings -> Fibonacci cluster. This is the key cluster/Convergence idea.
    cluster_levels: list[tuple[str, float]] = []
    relevant_count = min(6, len(lows) if trend == "BULLISH" else len(highs))
    swing_points = (lows if trend == "BULLISH" else highs)[-relevant_count:]
    for si, sv in swing_points:
        later = [h for h in highs if h[0] > si] if trend == "BULLISH" else [l for l in lows if l[0] > si]
        if not later:
            continue
        _, endv = later[-1]
        if abs(endv-sv) <= max(atr*0.8, price*0.0004):
            continue
        for r in RETRACEMENTS:
            cluster_levels.append((f"{si}:{r}", _fib_price(sv, endv, r, trend)))
    nearby_cluster = [x for x in cluster_levels if abs(price-x[1]) <= tol]
    cluster_count = len(nearby_cluster)
    fib_cluster = cluster_count >= 3

    # Horizontal support/resistance alignment.
    sr_levels = [("R", v) for _, v in highs[-12:]] + [("S", v) for _, v in lows[-12:]]
    sr_near = min(sr_levels, key=lambda x: abs(price-x[1]), default=("", None))
    sr_confluence = sr_near[1] is not None and abs(price-sr_near[1]) <= tol

    # Trendline approximation from two recent same-side swings.
    line_confluence = False
    line_value = None
    if trend == "BULLISH" and len(lows) >= 2:
        p1, p2 = lows[-2], lows[-1]
        if p2[0] > p1[0]:
            slope = (p2[1]-p1[1])/(p2[0]-p1[0])
            line_value = p2[1] + slope * (len(closed)-1-p2[0])
            line_confluence = abs(price-line_value) <= max(tol, atr*0.45)
    elif trend == "BEARISH" and len(highs) >= 2:
        p1, p2 = highs[-2], highs[-1]
        if p2[0] > p1[0]:
            slope = (p2[1]-p1[1])/(p2[0]-p1[0])
            line_value = p2[1] + slope * (len(closed)-1-p2[0])
            line_confluence = abs(price-line_value) <= max(tol, atr*0.45)

    last = closed[-1]
    prev = closed[-2]
    pin = _pinbar(last, bullish=trend == "BULLISH")
    price_action = pin or _crossed_level(_f(prev, "close", price) or price, price, sr_near[1], trend) if sr_near[1] is not None else pin

    # Fibo Musang setup: dominant candle or nearest S/R break + retest.
    dominant = _dominant_candle(closed)
    dominant_break = False
    dominant_index = None
    dominant_range = None
    musang_fib = None
    musang_entry_zone = None
    musang_cycle_hit = None
    if dominant:
        di, dc = dominant
        dh, dl = _f(dc, "high"), _f(dc, "low")
        dclose = _f(dc, "close")
        if dh is not None and dl is not None and dclose is not None:
            dominant_index = di
            dominant_range = round(dh-dl, 5)
            after = closed[di+1:]
            for cc in after:
                cclose = _f(cc, "close")
                if cclose is None:
                    continue
                if trend == "BULLISH" and cclose > dh:
                    dominant_break = True
                    break
                if trend == "BEARISH" and cclose < dl:
                    dominant_break = True
                    break
            if dominant_break:
                anchor_a = dl if trend == "BULLISH" else dh
                anchor_b = dh if trend == "BULLISH" else dl
                musang_fib = {str(r): round(_extension_price(anchor_a, anchor_b, r, trend), 5) for r in (1.618,2.618,4.236)}
                musang_cycle_hit = min(musang_fib.items(), key=lambda kv: abs(price-kv[1]))
                musang_entry_zone = abs(price-(anchor_b)) <= max(tol*1.5, atr*0.55)

    nearest_sr_break = False
    if sr_near[1] is not None:
        prev_close = _f(prev, "close")
        if prev_close is not None:
            nearest_sr_break = _crossed_level(prev_close, price, float(sr_near[1]), trend)

    musang_valid = bool((dominant_break or nearest_sr_break) and (musang_entry_zone or fib_near or fib_cluster or sr_confluence))

    mtf_dir = _mtf_direction(higher_frames)
    mtf_match = mtf_dir in {"NEUTRAL", trend}

    score = 0
    score += 15 if trend in {"BULLISH", "BEARISH"} else 0
    score += 15 if fib_near else 0
    score += 20 if fib_cluster else 0
    score += 10 if sr_confluence else 0
    score += 10 if line_confluence else 0
    score += 10 if price_action else 0
    score += 10 if musang_valid else 0
    score += 5 if mtf_match else 0
    score += 5 if (not high_volatility or fib_cluster) else 0

    # Candidate direction needs an active correction/reaction at the Fibonacci zone.
    reaction = fib_near and (pin or sr_confluence or line_confluence or nearest_fib[0] in {"0.5", "0.618", "0.786"})
    raw_direction = trend if reaction or fib_cluster or musang_valid else "WAIT"

    # Stop uses the prior swing origin / conservative invalidation. Targets use extensions.
    entry = stop = None
    targets: list[float] = []
    rr = 0.0
    if raw_direction in {"BULLISH", "BEARISH"}:
        entry = price
        if raw_direction == "BULLISH":
            stop = av - max(atr * 0.15, price * 0.00015)
            future_targets = sorted([v for v in exts.values() if v > entry])
            targets = future_targets[:3]
        else:
            stop = av + max(atr * 0.15, price * 0.00015)
            future_targets = sorted([v for v in exts.values() if v < entry], reverse=True)
            targets = future_targets[:3]
        if targets and stop is not None:
            rr = abs(targets[0]-entry) / max(abs(entry-stop), atr*0.35)
            if rr < 1.40 and len(targets) > 1:
                rr = abs(targets[1]-entry) / max(abs(entry-stop), atr*0.35)

    hard_wait = high_volatility and not fib_cluster and not sr_confluence
    # External SignalX contract uses BUY/SELL. Keep BULLISH/BEARISH as internal trend labels only.
    deterministic_signal = ("BUY" if raw_direction == "BULLISH" else "SELL" if raw_direction == "BEARISH" else "WAIT") if score >= 75 and rr >= 1.40 and not hard_wait else "WAIT"

    reasons: list[str] = []
    reasons.append(f"Trend {trend}")
    if fib_near:
        reasons.append(f"Fibo {fib_zone_ratio:.3f} zone")
    if fib_cluster:
        reasons.append(f"Fibo cluster {cluster_count} relationships")
    if sr_confluence:
        reasons.append("Fibonacci + S/R confluence")
    if line_confluence:
        reasons.append("Fibonacci + trendline confluence")
    if pin:
        reasons.append("Pin Bar reaction")
    if dominant_break:
        reasons.append("Dominant Candle Break")
    if nearest_sr_break:
        reasons.append("Nearest S/R / CB1-style break")
    if high_volatility:
        reasons.append(f"Volatility ratio {volatility_ratio:.2f}")
    if hard_wait:
        reasons.append("High-volatility data-quality filter")
    if rr < 1.40:
        reasons.append(f"RR {rr:.2f} below 1.40")

    return {
        "signal": deterministic_signal,
        "raw_direction": raw_direction,
        "confidence": int(min(100, score)),
        "score": int(min(100, score)),
        "state": "READY_FOR_AI" if deterministic_signal in {"BUY", "SELL"} else "WAIT",
        "reason": "; ".join(dict.fromkeys(reasons)),
        "trend": trend,
        "current_price": round(price, 5),
        "swing": {"a_index": ai, "a_price": round(av,5), "b_index": bi, "b_price": round(bv,5)},
        "retracement": {k: round(v,5) for k,v in fibs.items()},
        "extensions": {k: round(v,5) for k,v in exts.items()},
        "nearest_fibonacci": {"ratio": nearest_fib[0], "price": round(nearest_fib[1],5), "distance": round(abs(price-nearest_fib[1]),5), "within_tolerance": fib_near},
        "fib_cluster": {"count": cluster_count, "qualified": fib_cluster, "levels": [{"source": s, "price": round(v,5)} for s,v in nearby_cluster[:8]]},
        "horizontal_confluence": {"type": sr_near[0], "price": round(sr_near[1],5) if sr_near[1] is not None else None, "qualified": sr_confluence},
        "trendline_confluence": {"price": round(line_value,5) if line_value is not None else None, "qualified": line_confluence},
        "price_action": {"pin_bar": pin, "qualified": price_action},
        "musang": {
            "dominant_candle": dominant_index,
            "dominant_range": dominant_range,
            "dominant_break": dominant_break,
            "nearest_sr_break": nearest_sr_break,
            "qualified": musang_valid,
            "cycle_levels": musang_fib or {},
            "nearest_cycle": {"ratio": musang_cycle_hit[0], "price": round(musang_cycle_hit[1],5)} if musang_cycle_hit else None,
        },
        "volatility": {"atr": round(atr,5), "median_range": round(median_range,5), "ratio": round(volatility_ratio,2), "high": high_volatility,
                       "canonical_data_note": "Forex broker High/Low differences can affect Fibonacci anchors during volatility; canonical TradingView/OANDA series is used by SignalX."},
        "mtf": {"direction": mtf_dir, "match": mtf_match},
        "entry": round(entry,5) if deterministic_signal in {"BUY", "SELL"} else None,
        "stop_loss": round(stop,5) if deterministic_signal in {"BUY", "SELL"} else None,
        "take_profit": [round(x,5) for x in targets] if deterministic_signal in {"BUY", "SELL"} else [],
        "risk_reward": round(rr,2),
        "checks": {
            "trend_structure": trend in {"BULLISH","BEARISH"},
            "fibonacci_retracement_zone": fib_near,
            "fibonacci_price_cluster": fib_cluster,
            "horizontal_sr_confluence": sr_confluence,
            "trendline_confluence": line_confluence,
            "price_action_confirmation": price_action,
            "fibomusang_setup": musang_valid,
            "mtf_alignment": mtf_match,
            "volatility_quality": not hard_wait,
            "rr_ge_1_40": rr >= 1.40,
        },
        "source_strategy": "8 Fibonacci/Fibo Musang books + deterministic confluence + AI validation",
    }
