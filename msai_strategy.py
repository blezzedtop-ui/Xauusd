from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import math


@dataclass
class Zone:
    kind: str
    level: float
    low: float
    high: float
    index: int
    fresh: bool
    touches: int
    miss: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "level": round(self.level, 5),
            "low": round(self.low, 5),
            "high": round(self.high, 5),
            "index": self.index,
            "fresh": self.fresh,
            "touches": self.touches,
            "miss": self.miss,
        }


def _f(c: dict[str, Any], key: str) -> float:
    return float(c[key])


def _body(c: dict[str, Any]) -> tuple[float, float]:
    return min(_f(c, "open"), _f(c, "close")), max(_f(c, "open"), _f(c, "close"))


def _atr(candles: list[dict[str, Any]], n: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    trs: list[float] = []
    start = max(1, len(candles) - n)
    for i in range(start, len(candles)):
        c, p = candles[i], candles[i - 1]
        trs.append(max(
            _f(c, "high") - _f(c, "low"),
            abs(_f(c, "high") - _f(p, "close")),
            abs(_f(c, "low") - _f(p, "close")),
        ))
    return sum(trs) / max(1, len(trs))


def _pct(a: float, b: float) -> float:
    return abs(a - b) / max(abs(b), 1e-9)


def _swings(candles: list[dict[str, Any]], left: int = 2, right: int = 2):
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    for i in range(left, len(candles) - right):
        hi = _f(candles[i], "high")
        lo = _f(candles[i], "low")
        win_h = [_f(candles[j], "high") for j in range(i - left, i + right + 1)]
        win_l = [_f(candles[j], "low") for j in range(i - left, i + right + 1)]
        if hi >= max(win_h):
            highs.append((i, hi))
        if lo <= min(win_l):
            lows.append((i, lo))
    return highs, lows


def _line_value(p1: tuple[int, float], p2: tuple[int, float], idx: int) -> float:
    if p2[0] == p1[0]:
        return p2[1]
    slope = (p2[1] - p1[1]) / (p2[0] - p1[0])
    return p1[1] + slope * (idx - p1[0])


def _find_snr(candles: list[dict[str, Any]]) -> tuple[list[Zone], list[Zone], float]:
    """Malaysian SNR from open/close transitions; wick is ignored for level creation."""
    atr = max(_atr(candles), _f(candles[-1], "close") * 0.00015)
    tol = max(atr * 0.18, _f(candles[-1], "close") * 0.00012)
    supports: list[Zone] = []
    resistances: list[Zone] = []
    # Scan recent body transitions. Newest transitions are preferred.
    for i in range(max(1, len(candles) - 80), len(candles) - 1):
        prev = candles[i - 1]
        nxt = candles[i]
        prev_bull = _f(prev, "close") > _f(prev, "open")
        prev_bear = _f(prev, "close") < _f(prev, "open")
        nxt_bull = _f(nxt, "close") > _f(nxt, "open")
        nxt_bear = _f(nxt, "close") < _f(nxt, "open")
        if not ((prev_bull and nxt_bear) or (prev_bear and nxt_bull)):
            continue
        # The book draws from close to next open. Use their center as the executable line,
        # while retaining the body interval as the zone.
        a = _f(prev, "close")
        b = _f(nxt, "open")
        level = (a + b) / 2.0
        lo, hi = min(a, b), max(a, b)
        # Count later wick touches and detect a MISS before the first touch.
        touches = 0
        first_touch = None
        for j in range(i + 1, len(candles)):
            c = candles[j]
            if _f(c, "low") - tol <= level <= _f(c, "high") + tol:
                touches += 1
                if first_touch is None:
                    first_touch = j
        miss = False
        if first_touch is not None and first_touch - i >= 3:
            # At least two following candles moved away without returning to the level.
            miss = all(
                not (_f(candles[k], "low") - tol <= level <= _f(candles[k], "high") + tol)
                for k in range(i + 1, first_touch)
            )
        fresh = touches == 0
        z = Zone("SUPPORT" if (prev_bear and nxt_bull) else "RESISTANCE", level, lo, hi, i, fresh, touches, miss)
        (supports if z.kind == "SUPPORT" else resistances).append(z)
    supports = sorted(supports, key=lambda z: (not z.fresh, -z.index))
    resistances = sorted(resistances, key=lambda z: (not z.fresh, -z.index))
    return supports, resistances, tol


def _nearest_zone(price: float, zones: list[Zone], prefer_fresh: bool = True) -> Zone | None:
    if not zones:
        return None
    filtered = [z for z in zones if z.level <= price] if zones[0].kind == "SUPPORT" else [z for z in zones if z.level >= price]
    if not filtered:
        filtered = zones
    filtered.sort(key=lambda z: ((0 if (prefer_fresh and z.fresh) else 1), abs(price - z.level), -z.index))
    return filtered[0]


def _rejection(candles: list[dict[str, Any]], zone: Zone | None, direction: str, tol: float) -> dict[str, Any]:
    if zone is None:
        return {"valid": False, "index": None, "wick_touch": False, "close_rejection": False}
    for idx in range(len(candles) - 1, max(-1, len(candles) - 5), -1):
        c = candles[idx]
        touch = _f(c, "low") <= zone.level + tol and _f(c, "high") >= zone.level - tol
        if not touch:
            continue
        if direction == "BUY":
            wick_touch = _f(c, "low") <= zone.level + tol
            close_rejection = _f(c, "close") > zone.level
        else:
            wick_touch = _f(c, "high") >= zone.level - tol
            close_rejection = _f(c, "close") < zone.level
        if wick_touch and close_rejection:
            return {"valid": True, "index": idx, "wick_touch": True, "close_rejection": True,
                    "level": zone.level, "candle_time": c.get("time")}
    return {"valid": False, "index": None, "wick_touch": False, "close_rejection": False, "level": zone.level}


def _liquidity_sweep(candles: list[dict[str, Any]], direction: str) -> dict[str, Any]:
    if len(candles) < 12:
        return {"valid": False, "type": "NONE", "level": None, "index": None}
    highs, lows = _swings(candles[:-2], 2, 2)
    recent_high = highs[-1][1] if highs else max(_f(c, "high") for c in candles[-12:-2])
    recent_low = lows[-1][1] if lows else min(_f(c, "low") for c in candles[-12:-2])
    start = max(2, len(candles) - 5)
    for i in range(len(candles) - 1, start - 1, -1):
        c = candles[i]
        if direction == "BUY" and _f(c, "low") < recent_low and _f(c, "close") > recent_low:
            return {"valid": True, "type": "SELL_SIDE_SWEEP", "level": recent_low, "index": i}
        if direction == "SELL" and _f(c, "high") > recent_high and _f(c, "close") < recent_high:
            return {"valid": True, "type": "BUY_SIDE_SWEEP", "level": recent_high, "index": i}
    return {"valid": False, "type": "NONE", "level": recent_high if direction == "SELL" else recent_low, "index": None}


def _engulfing(candles: list[dict[str, Any]], direction: str) -> dict[str, Any]:
    for i in range(len(candles) - 1, max(0, len(candles) - 5), -1):
        prev, cur = candles[i - 1], candles[i]
        p0, p1 = _body(prev); c0, c1 = _body(cur)
        if direction == "BUY":
            valid = _f(prev, "close") < _f(prev, "open") and _f(cur, "close") > _f(cur, "open") and c0 <= p0 and c1 >= p1
        else:
            valid = _f(prev, "close") > _f(prev, "open") and _f(cur, "close") < _f(cur, "open") and c0 <= p0 and c1 >= p1
        if valid:
            return {"valid": True, "index": i, "type": "BULLISH" if direction == "BUY" else "BEARISH", "candle_time": cur.get("time")}
    return {"valid": False, "index": None, "type": "NONE"}


def _trendline(candles: list[dict[str, Any]], direction: str, tol: float) -> dict[str, Any]:
    highs, lows = _swings(candles, 2, 2)
    atr = max(_atr(candles), _f(candles[-1], "close") * 0.00015)
    current = len(candles) - 1
    if direction == "BUY" and len(lows) >= 2:
        p1, p2 = lows[-2], lows[-1]
        if p2[1] > p1[1]:
            line = _line_value(p1, p2, current)
            touch = _f(candles[-1], "low") <= line + max(tol, atr * 0.35)
            reject = _f(candles[-1], "close") > line
            return {"valid": touch and reject, "type": "SUPPORT_TRENDLINE", "points": [p1, p2], "line": line,
                    "touch": touch, "rejection": reject}
    if direction == "SELL" and len(highs) >= 2:
        p1, p2 = highs[-2], highs[-1]
        if p2[1] < p1[1]:
            line = _line_value(p1, p2, current)
            touch = _f(candles[-1], "high") >= line - max(tol, atr * 0.35)
            reject = _f(candles[-1], "close") < line
            return {"valid": touch and reject, "type": "RESISTANCE_TRENDLINE", "points": [p1, p2], "line": line,
                    "touch": touch, "rejection": reject}
    return {"valid": False, "type": "NONE", "points": [], "line": None, "touch": False, "rejection": False}


def _hns_qml(candles: list[dict[str, Any]], direction: str) -> dict[str, Any]:
    highs, lows = _swings(candles, 2, 2)
    if direction == "SELL" and len(highs) >= 3:
        a, b, c = highs[-3:]
        shoulder_ok = _pct(a[1], c[1]) <= 0.035
        if b[1] > a[1] and b[1] > c[1] and shoulder_ok:
            return {"valid": True, "type": "HNS_QML", "points": [a[0], b[0], c[0]], "level": min(a[1], c[1])}
    if direction == "BUY" and len(lows) >= 3:
        a, b, c = lows[-3:]
        shoulder_ok = _pct(a[1], c[1]) <= 0.035
        if b[1] < a[1] and b[1] < c[1] and shoulder_ok:
            return {"valid": True, "type": "INVERSE_HNS_QML", "points": [a[0], b[0], c[0]], "level": max(a[1], c[1])}
    return {"valid": False, "type": "NONE", "points": [], "level": None}


def _breakout_retest(candles: list[dict[str, Any]], direction: str) -> dict[str, Any]:
    if len(candles) < 8:
        return {"breakout": False, "retest": False, "level": None, "index": None}
    window = candles[-8:-1]
    if direction == "BUY":
        level = max(_f(c, "high") for c in window)
        breakout_idx = next((i for i in range(len(candles) - 4, len(candles)) if _f(candles[i], "close") > level), None)
        if breakout_idx is not None:
            retest = any(_f(candles[i], "low") <= level and _f(candles[i], "close") >= level for i in range(breakout_idx + 1, len(candles)))
            return {"breakout": True, "retest": retest, "level": level, "index": breakout_idx}
    else:
        level = min(_f(c, "low") for c in window)
        breakout_idx = next((i for i in range(len(candles) - 4, len(candles)) if _f(candles[i], "close") < level), None)
        if breakout_idx is not None:
            retest = any(_f(candles[i], "high") >= level and _f(candles[i], "close") <= level for i in range(breakout_idx + 1, len(candles)))
            return {"breakout": True, "retest": retest, "level": level, "index": breakout_idx}
    return {"breakout": False, "retest": False, "level": level, "index": None}


def _direction(candles: list[dict[str, Any]]) -> str:
    if len(candles) < 20:
        return "NEUTRAL"
    closes = [_f(c, "close") for c in candles]
    a = sum(closes[-5:]) / 5
    b = sum(closes[-20:]) / 20
    highs, lows = _swings(candles[:-1], 2, 2)
    bull = len(highs) >= 2 and len(lows) >= 2 and highs[-1][1] > highs[-2][1] and lows[-1][1] > lows[-2][1]
    bear = len(highs) >= 2 and len(lows) >= 2 and highs[-1][1] < highs[-2][1] and lows[-1][1] < lows[-2][1]
    if bull and a > b:
        return "BULLISH"
    if bear and a < b:
        return "BEARISH"
    if a > b * 1.0003:
        return "BULLISH"
    if a < b * 0.9997:
        return "BEARISH"
    return "NEUTRAL"


def analyze_msai(
    candles: list[dict[str, Any]],
    mtf: dict[str, Any] | None = None,
    selected_interval: str = "5min",
) -> dict[str, Any]:
    if len(candles) < 50:
        return {
            "signal": "WAIT", "score": 0, "confidence": 0, "state": "INSUFFICIENT_DATA",
            "reason": "MSAI uchun yetarli candle mavjud emas.", "checks": {}, "setup": "WAIT",
            "entry": None, "stop_loss": None, "take_profit": [], "risk_reward": None,
        }

    price = _f(candles[-1], "close")
    atr = max(_atr(candles), price * 0.0002)
    supports, resistances, tol = _find_snr(candles)
    nearest_s = _nearest_zone(price, supports)
    nearest_r = _nearest_zone(price, resistances)

    # Determine the candidate side from the best SNR touch/rejection.
    buy_rej = _rejection(candles, nearest_s, "BUY", tol)
    sell_rej = _rejection(candles, nearest_r, "SELL", tol)
    if buy_rej["valid"] and not sell_rej["valid"]:
        direction = "BUY"
    elif sell_rej["valid"] and not buy_rej["valid"]:
        direction = "SELL"
    else:
        # Before a completed touch, keep the directional context as a watch state.
        higher = (mtf or {}).get("direction_bias") or "NEUTRAL"
        direction = "BUY" if higher == "BULLISH" and nearest_s else "SELL" if higher == "BEARISH" and nearest_r else "WAIT"

    if direction == "WAIT":
        return {
            "signal": "WAIT", "score": 0, "confidence": 0, "state": "WAIT_ZONE",
            "reason": "HTF/LTF SNR touch-rejection setup hali valid emas.", "checks": {
                "buy_rejection": buy_rej, "sell_rejection": sell_rej,
            }, "setup": "WAIT_ZONE", "entry": None, "stop_loss": None, "take_profit": [], "risk_reward": None,
            "snr": {"support": nearest_s.as_dict() if nearest_s else None, "resistance": nearest_r.as_dict() if nearest_r else None},
        }

    zone = nearest_s if direction == "BUY" else nearest_r
    rejection = buy_rej if direction == "BUY" else sell_rej
    sweep = _liquidity_sweep(candles, direction)
    engulf = _engulfing(candles, direction)
    trendline = _trendline(candles, direction, tol)
    hns_qml = _hns_qml(candles, direction)
    br = _breakout_retest(candles, direction)

    # Score = source-derived rule weights for implementation; not a win-rate.
    checks = {
        "storyline": bool((mtf or {}).get("alignment")),
        "fresh_snr": bool(zone and zone.fresh),
        "wick_rejection": bool(rejection.get("valid")),
        "liquidity_sweep": bool(sweep.get("valid")),
        "miss": bool(zone and zone.miss),
        "engulfing": bool(engulf.get("valid")),
        "trendline": bool(trendline.get("valid")),
        "qml_hns": bool(hns_qml.get("valid")),
        "breakout": bool(br.get("breakout")),
        "retest": bool(br.get("retest")),
    }
    score = 0
    score += 20 if checks["storyline"] else 0
    score += 15 if checks["fresh_snr"] else 0
    score += 15 if checks["wick_rejection"] else 0
    score += 10 if checks["liquidity_sweep"] else 0
    score += 5 if checks["miss"] else 0
    score += 15 if checks["engulfing"] else 0
    score += 10 if checks["trendline"] else 0
    score += 5 if checks["qml_hns"] else 0
    score += 5 if (checks["breakout"] and checks["retest"]) else 0

    # MTF alignment: direction must agree with the higher-timeframe storyline.
    htf_bias = str((mtf or {}).get("direction_bias") or "NEUTRAL")
    mtf_match = (direction == "BUY" and htf_bias == "BULLISH") or (direction == "SELL" and htf_bias == "BEARISH")
    checks["mtf_match"] = mtf_match
    if not mtf_match:
        score = max(0, score - 15)

    # Entry levels: rejection structure, then a conservative target on the next opposing level.
    recent_high = max(_f(c, "high") for c in candles[-12:])
    recent_low = min(_f(c, "low") for c in candles[-12:])
    if direction == "BUY":
        sl = min(recent_low, zone.low if zone else recent_low) - atr * 0.15
        risk = max(price - sl, atr * 0.6)
        opposing = nearest_r.level if nearest_r and nearest_r.level > price else None
        tp1 = opposing if opposing and (opposing - price) / risk >= 1.5 else price + risk * 2.0
        tp2 = max(tp1, price + risk * 3.0)
        rr = (tp1 - price) / risk
    else:
        sl = max(recent_high, zone.high if zone else recent_high) + atr * 0.15
        risk = max(sl - price, atr * 0.6)
        opposing = nearest_s.level if nearest_s and nearest_s.level < price else None
        tp1 = opposing if opposing and (price - opposing) / risk >= 1.5 else price - risk * 2.0
        tp2 = min(tp1, price - risk * 3.0)
        rr = (price - tp1) / risk

    # Book-faithful hard execution gate: validation + LTF confirmation + MTF agreement.
    critical = checks["wick_rejection"] and checks["engulfing"] and checks["mtf_match"] and checks["breakout"]
    confirmed = critical and score >= 75 and rr >= 1.40
    signal = direction if confirmed else "WAIT"
    state = "CONFIRMED" if confirmed else "WAIT_VALIDATION"

    reasons: list[str] = []
    if checks["fresh_snr"]: reasons.append("Fresh Malaysian SNR")
    if checks["wick_rejection"]: reasons.append("wick rejection")
    if checks["liquidity_sweep"]: reasons.append(sweep.get("type", "liquidity sweep"))
    if checks["miss"]: reasons.append("MISS")
    if checks["engulfing"]: reasons.append(f"{engulf.get('type')} engulfing")
    if checks["trendline"]: reasons.append("SNR + Trendline confluence")
    if checks["qml_hns"]: reasons.append(hns_qml.get("type", "QML/HNS"))
    if checks["breakout"]: reasons.append("LTF breakout")
    if checks["retest"]: reasons.append("retest")
    if not mtf_match: reasons.append(f"MTF conflict: {htf_bias}")
    if not confirmed: reasons.append("NO VALIDATION, NO TRADE")

    return {
        "signal": signal,
        "raw_direction": direction,
        "score": int(score),
        "confidence": int(min(99, max(25, score))),
        "state": state,
        "setup": "MSAI_CONFIRMATION" if confirmed else "WAIT_VALIDATION",
        "reason": "; ".join(dict.fromkeys(reasons)) or "MSAI setup incomplete.",
        "checks": checks,
        "entry": round(price, 5) if signal != "WAIT" else None,
        "stop_loss": round(sl, 5) if signal != "WAIT" else None,
        "take_profit": [round(tp1, 5), round(tp2, 5)] if signal != "WAIT" else [],
        "risk_reward": round(rr, 2) if signal != "WAIT" else round(rr, 2),
        "snr": {"support": nearest_s.as_dict() if nearest_s else None, "resistance": nearest_r.as_dict() if nearest_r else None,
                "active_zone": zone.as_dict() if zone else None, "tolerance": round(tol, 5)},
        "rejection": rejection,
        "liquidity": sweep,
        "engulfing": engulf,
        "trendline": trendline,
        "qml_hns": hns_qml,
        "breakout": br,
        "atr": round(atr, 5),
        "price": round(price, 5),
        "selected_interval": selected_interval,
    }


def summarize_mtf(timeframes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    order = ["1day", "4h", "1h", "30min", "15min", "5min", "1min"]
    labels = {"1day": "Daily", "4h": "H4", "1h": "H1", "30min": "M30", "15min": "M15", "5min": "M5", "1min": "M1"}
    rows = []
    for tf in order:
        x = timeframes.get(tf) or {}
        trend = str(x.get("trend") or "NEUTRAL")
        rows.append({"interval": tf, "label": labels[tf], "trend": trend, "price": x.get("price"), "rsi": x.get("rsi")})
    dirs = [r["trend"] for r in rows if r["trend"] in {"BULLISH", "BEARISH"}]
    bull = dirs.count("BULLISH"); bear = dirs.count("BEARISH")
    bias = "BULLISH" if bull >= 3 and bull > bear else "BEARISH" if bear >= 3 and bear > bull else "NEUTRAL"
    alignment = (bull >= 4 if bias == "BULLISH" else bear >= 4 if bias == "BEARISH" else False)
    return {"rows": rows, "direction_bias": bias, "alignment": alignment, "bullish_count": bull, "bearish_count": bear}


def direction_from_candles(candles: list[dict[str, Any]]) -> str:
    return _direction(candles)


def aggregate_weekly(daily: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build synthetic weekly OHLC from daily candles when a weekly feed is unavailable."""
    if not daily:
        return []
    groups: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for c in daily:
        raw = c.get("time")
        try:
            if isinstance(raw, (int, float)):
                from datetime import datetime, timezone
                dt = datetime.fromtimestamp(float(raw) / 1000 if float(raw) > 2e10 else float(raw), tz=timezone.utc)
            else:
                s = str(raw).replace("Z", "+00:00")
                from datetime import datetime, timezone
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            key = (dt.isocalendar().year, dt.isocalendar().week)
        except Exception:
            key = (0, 0)
        groups.setdefault(key, []).append(c)
    out: list[dict[str, Any]] = []
    for key, items in sorted(groups.items()):
        if key == (0, 0):
            continue
        out.append({
            "time": items[-1].get("time"),
            "open": _f(items[0], "open"),
            "high": max(_f(x, "high") for x in items),
            "low": min(_f(x, "low") for x in items),
            "close": _f(items[-1], "close"),
        })
    return out


def lower_timeframe_confirmation(candles: list[dict[str, Any]], direction: str) -> dict[str, Any]:
    """Two-TF confirmation: LTF engulfing plus breakout/retest in the direction of the HTF setup."""
    engulf = _engulfing(candles, direction)
    br = _breakout_retest(candles, direction)
    return {
        "engulfing": engulf,
        "breakout": br,
        "valid": bool(engulf.get("valid") and br.get("breakout")),
        "retest": bool(br.get("retest")),
    }
