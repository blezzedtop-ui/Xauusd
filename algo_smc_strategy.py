from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import mean
from typing import Any
from zoneinfo import ZoneInfo


@dataclass
class Swing:
    index: int
    price: float


def _f(c: dict[str, Any], key: str) -> float:
    return float(c.get(key, 0.0))


def _time(c: dict[str, Any]) -> datetime | None:
    v = c.get("time")
    try:
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(float(v), timezone.utc)
        s = str(v or "")
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


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
    return mean(trs) if trs else 0.0


def _swings(candles: list[dict[str, Any]], left: int = 2, right: int = 2) -> tuple[list[Swing], list[Swing]]:
    highs: list[Swing] = []
    lows: list[Swing] = []
    for i in range(left, len(candles) - right):
        hi = _f(candles[i], "high")
        lo = _f(candles[i], "low")
        window_hi = max(_f(candles[j], "high") for j in range(i - left, i + right + 1))
        window_lo = min(_f(candles[j], "low") for j in range(i - left, i + right + 1))
        if hi >= window_hi:
            highs.append(Swing(i, hi))
        if lo <= window_lo:
            lows.append(Swing(i, lo))
    return highs, lows


def _direction_from_swings(candles: list[dict[str, Any]]) -> str:
    highs, lows = _swings(candles)
    if len(highs) >= 2 and len(lows) >= 2:
        hh = highs[-1].price > highs[-2].price
        hl = lows[-1].price > lows[-2].price
        lh = highs[-1].price < highs[-2].price
        ll = lows[-1].price < lows[-2].price
        if hh and hl:
            return "BULLISH"
        if lh and ll:
            return "BEARISH"
    if len(candles) >= 20:
        close = _f(candles[-1], "close")
        avg = mean(_f(c, "close") for c in candles[-11:-1])
        if close > avg * 1.0005:
            return "BULLISH"
        if close < avg * 0.9995:
            return "BEARISH"
    return "NEUTRAL"


def _structure(candles: list[dict[str, Any]]) -> dict[str, Any]:
    highs, lows = _swings(candles)
    price = _f(candles[-1], "close")
    last_high = highs[-1] if highs else None
    last_low = lows[-1] if lows else None
    prev_high = highs[-2] if len(highs) >= 2 else None
    prev_low = lows[-2] if len(lows) >= 2 else None
    trend = _direction_from_swings(candles)

    bullish_break = bool(last_high and price > last_high.price)
    bearish_break = bool(last_low and price < last_low.price)
    bos = "BULLISH" if bullish_break else "BEARISH" if bearish_break else "NONE"

    choch = "NONE"
    if trend == "BEARISH" and bullish_break:
        choch = "BULLISH"
    elif trend == "BULLISH" and bearish_break:
        choch = "BEARISH"

    # Strong high/low = swing that is followed by a meaningful opposite structure break.
    strong_high = None
    for h in reversed(highs[-8:]):
        post = candles[h.index + 1 : min(len(candles), h.index + 35)]
        if prev_low and any(_f(c, "close") < prev_low.price for c in post):
            strong_high = h
            break
    strong_low = None
    for l in reversed(lows[-8:]):
        post = candles[l.index + 1 : min(len(candles), l.index + 35)]
        if prev_high and any(_f(c, "close") > prev_high.price for c in post):
            strong_low = l
            break

    return {
        "trend": trend,
        "bos": bos,
        "choch": choch,
        "last_high": last_high.price if last_high else None,
        "last_low": last_low.price if last_low else None,
        "strong_high": strong_high.price if strong_high else None,
        "strong_low": strong_low.price if strong_low else None,
        "weak_high": last_high.price if last_high and (not strong_high or abs(last_high.price - strong_high.price) > 1e-9) else None,
        "weak_low": last_low.price if last_low and (not strong_low or abs(last_low.price - strong_low.price) > 1e-9) else None,
        "swing_highs": [{"index": x.index, "price": round(x.price, 5)} for x in highs[-8:]],
        "swing_lows": [{"index": x.index, "price": round(x.price, 5)} for x in lows[-8:]],
    }


def _aggregate(candles: list[dict[str, Any]], bucket: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for c in candles:
        dt = _time(c)
        if not dt:
            continue
        if bucket == "week":
            key = f"{dt.isocalendar().year}-W{dt.isocalendar().week:02d}"
        else:
            key = f"{dt.year}-{dt.month:02d}"
        groups.setdefault(key, []).append(c)
    out: list[dict[str, Any]] = []
    for key, rows in groups.items():
        out.append({
            "time": rows[0].get("time"),
            "open": _f(rows[0], "open"),
            "high": max(_f(x, "high") for x in rows),
            "low": min(_f(x, "low") for x in rows),
            "close": _f(rows[-1], "close"),
            "volume": sum(float(x.get("volume") or 0) for x in rows),
            "bucket": key,
        })
    return out


def _liquidity_levels(daily: list[dict[str, Any]], hourly: list[dict[str, Any]], current_price: float) -> dict[str, Any]:
    def hi(rows):
        return max((_f(x, "high") for x in rows), default=None)
    def lo(rows):
        return min((_f(x, "low") for x in rows), default=None)

    weekly = _aggregate(daily, "week")
    monthly = _aggregate(daily, "month")

    prev_daily = daily[-2] if len(daily) >= 2 else daily[-1]
    prev_week = weekly[-2] if len(weekly) >= 2 else weekly[-1] if weekly else None
    prev_month = monthly[-2] if len(monthly) >= 2 else monthly[-1] if monthly else None
    previous_year_rows: list[dict[str, Any]] = []
    if daily:
        cur_year = _time(daily[-1]).year if _time(daily[-1]) else None
        previous_year_rows = [c for c in daily if (_time(c) and _time(c).year == cur_year - 1)] if cur_year else []

    major = {
        "PDH": _f(prev_daily, "high"), "PDL": _f(prev_daily, "low"),
        "PWH": _f(prev_week, "high") if prev_week else None, "PWL": _f(prev_week, "low") if prev_week else None,
        "PMH": _f(prev_month, "high") if prev_month else None, "PML": _f(prev_month, "low") if prev_month else None,
        "PYH": hi(previous_year_rows), "PYL": lo(previous_year_rows),
    }
    med_hi = hi(hourly[-80:]) if hourly else None
    med_lo = lo(hourly[-80:]) if hourly else None
    minor_hi = hi(hourly[-12:]) if hourly else None
    minor_lo = lo(hourly[-12:]) if hourly else None

    buy_targets = sorted({v for v in major.values() if isinstance(v, (int, float)) and v > current_price})
    sell_targets = sorted({v for v in major.values() if isinstance(v, (int, float)) and v < current_price}, reverse=True)
    return {
        "major": major,
        "medium": {"high": med_hi, "low": med_lo},
        "minor": {"high": minor_hi, "low": minor_lo},
        "nearest_buy_side": buy_targets[0] if buy_targets else None,
        "nearest_sell_side": sell_targets[0] if sell_targets else None,
    }


def _sweep(candles: list[dict[str, Any]], structure: dict[str, Any], liq: dict[str, Any], atr: float) -> dict[str, Any]:
    recent = candles[-8:]
    buy_side_levels = [x for x in [liq["major"].get("PDH"), liq["major"].get("PWH"), liq["major"].get("PMH"), structure.get("last_high")] if x is not None]
    sell_side_levels = [x for x in [liq["major"].get("PDL"), liq["major"].get("PWL"), liq["major"].get("PML"), structure.get("last_low")] if x is not None]
    best = {"valid": False, "side": "NONE", "level": None, "index": None}
    for i, c in reversed(list(enumerate(recent))):
        hi, lo, cl = _f(c, "high"), _f(c, "low"), _f(c, "close")
        for lvl in buy_side_levels:
            if hi > float(lvl) + atr * 0.05 and cl < float(lvl):
                return {"valid": True, "side": "BUY_SIDE", "level": round(float(lvl), 5), "index": len(candles) - len(recent) + i}
        for lvl in sell_side_levels:
            if lo < float(lvl) - atr * 0.05 and cl > float(lvl):
                return {"valid": True, "side": "SELL_SIDE", "level": round(float(lvl), 5), "index": len(candles) - len(recent) + i}
    return best


def _fvg(candles: list[dict[str, Any]], atr: float) -> dict[str, Any]:
    for i in range(len(candles) - 1, 1, -1):
        a, b, c = candles[i - 2], candles[i - 1], candles[i]
        if _f(c, "low") > _f(a, "high") and (_f(c, "low") - _f(a, "high")) >= atr * 0.05:
            return {"valid": True, "type": "BULLISH", "low": _f(a, "high"), "high": _f(c, "low"), "index": i}
        if _f(c, "high") < _f(a, "low") and (_f(a, "low") - _f(c, "high")) >= atr * 0.05:
            return {"valid": True, "type": "BEARISH", "low": _f(c, "high"), "high": _f(a, "low"), "index": i}
    return {"valid": False, "type": "NONE", "low": None, "high": None, "index": None}


def _displacement(candles: list[dict[str, Any]], atr: float) -> dict[str, Any]:
    c = candles[-1]
    body = abs(_f(c, "close") - _f(c, "open"))
    return {
        "bullish": _f(c, "close") > _f(c, "open") and body >= atr * 1.15,
        "bearish": _f(c, "close") < _f(c, "open") and body >= atr * 1.15,
        "body_atr": round(body / max(atr, 1e-9), 2),
    }


def _amd(candles: list[dict[str, Any]], atr: float) -> dict[str, Any]:
    look = candles[-12:]
    if len(look) < 8:
        return {"phase": "UNKNOWN", "range_high": None, "range_low": None, "build_up": False, "manipulation": False, "distribution": False}
    rh = max(_f(c, "high") for c in look[:-2])
    rl = min(_f(c, "low") for c in look[:-2])
    recent_range = rh - rl
    build = recent_range <= atr * 5.0
    last = candles[-1]
    manipulation = (_f(last, "high") > rh and _f(last, "close") < rh) or (_f(last, "low") < rl and _f(last, "close") > rl)
    disp = _displacement(candles, atr)
    distribution = disp["bullish"] or disp["bearish"]
    phase = "MANIPULATION" if manipulation else "DISTRIBUTION" if distribution else "ACCUMULATION" if build else "TRANSITION"
    return {"phase": phase, "range_high": rh, "range_low": rl, "build_up": build, "manipulation": manipulation, "distribution": distribution}


def _premium_discount(daily: list[dict[str, Any]], current_price: float) -> dict[str, Any]:
    if not daily:
        return {"zone": "UNKNOWN", "daily_open": None, "range_mid": None}
    d = daily[-1]
    op = _f(d, "open")
    mid = (_f(d, "high") + _f(d, "low")) / 2.0
    # The source explicitly uses Daily Open to distinguish discount/premium.
    zone = "DISCOUNT" if current_price < op else "PREMIUM" if current_price > op else "AT_DAILY_OPEN"
    midpoint = "DISCOUNT" if current_price < mid else "PREMIUM" if current_price > mid else "EQUILIBRIUM"
    return {"zone": zone, "midpoint_zone": midpoint, "daily_open": op, "range_mid": mid}


def _fake_structure_break(candles: list[dict[str, Any]], structure: dict[str, Any], atr: float) -> dict[str, Any]:
    # FBMS heuristic: recent break beyond a swing followed by a close back into the prior range.
    if len(candles) < 6:
        return {"valid": False, "direction": "NONE", "reason": "insufficient_history"}
    highs, lows = _swings(candles[:-2])
    last = candles[-1]
    for h in reversed(highs[-4:]):
        for i in range(h.index + 1, len(candles)):
            c = candles[i]
            if _f(c, "high") > h.price + atr * 0.05 and _f(c, "close") < h.price:
                return {"valid": True, "direction": "BEARISH", "level": h.price, "reason": "break above swing high without acceptance"}
    for l in reversed(lows[-4:]):
        for i in range(l.index + 1, len(candles)):
            c = candles[i]
            if _f(c, "low") < l.price - atr * 0.05 and _f(c, "close") > l.price:
                return {"valid": True, "direction": "BULLISH", "level": l.price, "reason": "break below swing low without acceptance"}
    return {"valid": False, "direction": "NONE", "level": None, "reason": "no obvious fake break"}



def _order_block(candles: list[dict[str, Any]], direction: str, atr: float) -> dict[str, Any]:
    start=max(2,len(candles)-35)
    for i in range(len(candles)-2,start-1,-1):
        cur=candles[i]; nxt=candles[i+1]
        if abs(_f(nxt,"close")-_f(nxt,"open")) < atr*1.0:
            continue
        if direction=="BUY" and _f(cur,"close")<_f(cur,"open") and _f(nxt,"close")>_f(nxt,"open"):
            return {"valid":True,"type":"BULLISH_OB","low":_f(cur,"low"),"high":_f(cur,"high"),"index":i}
        if direction=="SELL" and _f(cur,"close")>_f(cur,"open") and _f(nxt,"close")<_f(nxt,"open"):
            return {"valid":True,"type":"BEARISH_OB","low":_f(cur,"low"),"high":_f(cur,"high"),"index":i}
    return {"valid":False,"type":"NONE","low":None,"high":None,"index":None}


def _breaker_block(candles: list[dict[str, Any]], direction: str, ob: dict[str, Any], atr: float) -> dict[str, Any]:
    if not ob.get("valid"):
        return {"valid":False,"type":"NONE","low":None,"high":None,"index":None,"retest":False}
    low,high=float(ob["low"]),float(ob["high"])
    broken=False; break_index=None
    for i in range(int(ob["index"])+1,len(candles)):
        cl=_f(candles[i],"close")
        if direction=="BUY" and cl < low-atr*0.05:
            broken=True; break_index=i; break
        if direction=="SELL" and cl > high+atr*0.05:
            broken=True; break_index=i; break
    if not broken:
        return {"valid":False,"type":"NONE","low":low,"high":high,"index":ob.get("index"),"retest":False}
    retest=False
    for c in candles[break_index+1:]:
        if _f(c,"low")<=high and _f(c,"high")>=low:
            if direction=="BUY" and _f(c,"close")>high: retest=True
            if direction=="SELL" and _f(c,"close")<low: retest=True
    return {"valid":True,"type":"BULLISH_BREAKER" if direction=="BUY" else "BEARISH_BREAKER","low":low,"high":high,"index":break_index,"retest":retest}


def _rejection_block(candles: list[dict[str, Any]], direction: str, sweep: dict[str, Any], atr: float) -> dict[str, Any]:
    c=candles[-1]; rng=max(_f(c,"high")-_f(c,"low"),1e-9)
    upper=_f(c,"high")-max(_f(c,"open"),_f(c,"close")); lower=min(_f(c,"open"),_f(c,"close"))-_f(c,"low")
    wick_ratio=max(upper,lower)/rng
    valid=bool(sweep.get("valid") and wick_ratio>=0.45 and rng>=atr*0.75)
    return {"valid":valid,"type":"BULLISH_REJECTION" if direction=="BUY" and valid else "BEARISH_REJECTION" if direction=="SELL" and valid else "NONE","index":len(candles)-1,"wick_ratio":round(wick_ratio,2)}


def _hvi(candles: list[dict[str, Any]]) -> dict[str, Any]:
    vols=[float(c.get("volume") or 0) for c in candles[-25:]]
    prior=[v for v in vols[:-1] if v>0]
    if not prior or vols[-1]<=0:
        return {"valid":False,"ratio":None,"note":"volume unavailable"}
    ratio=vols[-1]/mean(prior)
    return {"valid":ratio>=1.5,"ratio":round(ratio,2),"note":"latest volume / prior average"}


def _entry_modules(candles: list[dict[str, Any]], direction: str, structure: dict[str, Any], sweep: dict[str, Any], fvg: dict[str, Any], amd: dict[str, Any], premium: dict[str, Any], atr: float) -> dict[str, Any]:
    last = candles[-1]
    prev = candles[-2]
    body_lo = min(_f(last, "open"), _f(last, "close"))
    body_hi = max(_f(last, "open"), _f(last, "close"))
    prev_lo = min(_f(prev, "open"), _f(prev, "close"))
    prev_hi = max(_f(prev, "open"), _f(prev, "close"))
    bull_eng = _f(last, "close") > _f(last, "open") and body_lo <= prev_lo and body_hi >= prev_hi and _f(prev, "close") < _f(prev, "open")
    bear_eng = _f(last, "close") < _f(last, "open") and body_lo <= prev_lo and body_hi >= prev_hi and _f(prev, "close") > _f(prev, "open")
    engulf = bull_eng if direction == "BUY" else bear_eng

    sweep_dir = "BUY" if sweep.get("side") == "SELL_SIDE" else "SELL" if sweep.get("side") == "BUY_SIDE" else "WAIT"
    bos_match = (structure.get("bos") == ("BULLISH" if direction == "BUY" else "BEARISH")) or (structure.get("choch") == ("BULLISH" if direction == "BUY" else "BEARISH"))
    fvg_match = fvg.get("valid") and fvg.get("type") == ("BULLISH" if direction == "BUY" else "BEARISH")
    displacement = _displacement(candles, atr)
    algo_candle = bool(sweep.get("valid") and ((direction == "BUY" and displacement["bullish"]) or (direction == "SELL" and displacement["bearish"])))
    discount_ok = premium.get("zone") == ("DISCOUNT" if direction == "BUY" else "PREMIUM")

    # Previous candle liquidity module from the source.
    prev_sweep = (direction == "BUY" and _f(last, "low") < _f(prev, "low") and _f(last, "close") > _f(prev, "low")) or (direction == "SELL" and _f(last, "high") > _f(prev, "high") and _f(last, "close") < _f(prev, "high"))
    ping_pong = bool(amd.get("manipulation") and (engulf or algo_candle or bos_match))
    return {
        "liquidity_shift": sweep_dir == direction,
        "algo_candle": algo_candle,
        "fvg_confirmation": bool(fvg_match),
        "bos_choch_confirmation": bool(bos_match),
        "engulfing_confirmation": bool(engulf),
        "previous_candle_liquidity": bool(prev_sweep),
        "ping_pong": ping_pong,
        "premium_discount_alignment": bool(discount_ok),
        "displacement": bool(displacement["bullish"] if direction == "BUY" else displacement["bearish"]),
    }


def _nearest_target(liquidity: dict[str, Any], direction: str, price: float, atr: float) -> tuple[float | None, float | None]:
    major_vals = [v for v in liquidity.get("major", {}).values() if isinstance(v, (int, float))]
    if direction == "BUY":
        above = sorted(v for v in major_vals if v > price + atr * 0.15)
        return (above[0] if above else liquidity.get("nearest_buy_side"), above[1] if len(above) > 1 else None)
    below = sorted((v for v in major_vals if v < price - atr * 0.15), reverse=True)
    return (below[0] if below else liquidity.get("nearest_sell_side"), below[1] if len(below) > 1 else None)


def _weekly_cycle(dt: datetime | None) -> dict[str, Any]:
    if not dt:
        return {"phase":"UNKNOWN"}
    phases={0:"MONDAY_MANIPULATION",1:"TUESDAY_ACCUMULATION_CONTINUATION",2:"WEDNESDAY_REACCUMULATION_OR_REVERSAL",3:"THURSDAY_COMPLETION",4:"FRIDAY_DISTRIBUTION"}
    return {"phase":phases.get(dt.weekday(),"WEEKEND"),"weekday":dt.strftime("%A")}


def _ninety_minute_cycle(dt: datetime | None) -> dict[str, Any]:
    if not dt:
        return {"valid":False}
    ny=dt.astimezone(ZoneInfo("America/New_York"))
    minutes=ny.hour*60+ny.minute
    block=(minutes//90)
    start=block*90
    start_h=(start//60)%24;start_m=start%60
    return {"valid":True,"anchor":"NY 00:00","block_index":block,"block_start":f"{start_h:02d}:{start_m:02d}","minutes_into_block":minutes-start}


def analyze_algo_smc(
    selected: list[dict[str, Any]],
    daily: list[dict[str, Any]],
    hourly: list[dict[str, Any]],
    mtf: dict[str, Any] | None = None,
    selected_interval: str = "5min",
) -> dict[str, Any]:
    if len(selected) < 60 or len(daily) < 20 or len(hourly) < 40:
        return {
            "signal": "WAIT", "raw_direction": "WAIT", "state": "INSUFFICIENT_DATA", "score": 0, "confidence": 0,
            "reason": "Algo/SMC uchun yetarli multi-timeframe candle mavjud emas.", "checks": {}, "entry": None, "stop_loss": None, "take_profit": [], "risk_reward": None,
        }

    price = _f(selected[-1], "close")
    atr = max(_atr(selected), price * 0.0002)
    structure = _structure(selected)
    liquidity = _liquidity_levels(daily, hourly, price)
    sweep = _sweep(selected, structure, liquidity, atr)
    fvg = _fvg(selected, atr)
    amd = _amd(selected, atr)
    premium = _premium_discount(daily, price)
    fake = _fake_structure_break(selected, structure, atr)
    displacement = _displacement(selected, atr)
    last_dt = _time(selected[-1])
    weekly_cycle = _weekly_cycle(last_dt)
    cycle_90m = _ninety_minute_cycle(last_dt)

    htf_rows = (mtf or {}).get("rows") or []
    htf_direction = str((mtf or {}).get("direction_bias") or "NEUTRAL")
    raw_direction = "WAIT"
    if structure.get("choch") in {"BULLISH", "BEARISH"}:
        raw_direction = "BUY" if structure["choch"] == "BULLISH" else "SELL"
    elif structure.get("bos") in {"BULLISH", "BEARISH"}:
        raw_direction = "BUY" if structure["bos"] == "BULLISH" else "SELL"
    elif structure.get("trend") in {"BULLISH", "BEARISH"}:
        raw_direction = "BUY" if structure["trend"] == "BULLISH" else "SELL"
    if htf_direction in {"BULLISH", "BEARISH"} and raw_direction in {"BUY", "SELL"}:
        if (htf_direction == "BULLISH" and raw_direction == "SELL") or (htf_direction == "BEARISH" and raw_direction == "BUY"):
            raw_direction = "WAIT"

    if raw_direction not in {"BUY", "SELL"}:
        return {
            "signal": "WAIT", "raw_direction": raw_direction, "state": "WAIT_DIRECTION", "score": 0, "confidence": 0,
            "reason": "HTF storyline va local structure hali bir yo‘nalishda tasdiqlanmadi.",
            "checks": {"htf_direction": bool(htf_direction in {"BULLISH", "BEARISH"}), "structure": False},
            "entry": None, "stop_loss": None, "take_profit": [], "risk_reward": None,
            "structure": structure, "liquidity": liquidity, "sweep": sweep, "fvg": fvg, "amd": amd, "premium_discount": premium, "fake_break": fake,
        }

    direction = raw_direction
    order_block = _order_block(selected, direction, atr)
    breaker_block = _breaker_block(selected, direction, order_block, atr)
    rejection_block = _rejection_block(selected, direction, sweep, atr)
    hvi = _hvi(selected)
    modules = _entry_modules(selected, direction, structure, sweep, fvg, amd, premium, atr)
    modules["order_block"] = bool(order_block.get("valid"))
    modules["breaker_retest"] = bool(breaker_block.get("valid") and breaker_block.get("retest"))
    modules["rejection_block"] = bool(rejection_block.get("valid"))
    modules["hvi"] = bool(hvi.get("valid"))

    # Source-derived scoring dimensions; exact numeric thresholds are SignalX implementation choices.
    liquidity_ok = bool(sweep.get("valid"))
    shift_ok = bool(modules["liquidity_shift"] or modules["bos_choch_confirmation"] or modules["algo_candle"])
    poi_ok = bool(fvg.get("valid") or modules["algo_candle"] or order_block.get("valid") or breaker_block.get("valid") or rejection_block.get("valid"))
    confirmation_ok = bool(modules["bos_choch_confirmation"] or modules["engulfing_confirmation"] or modules["previous_candle_liquidity"] or modules["fvg_confirmation"] or modules["breaker_retest"] or modules["rejection_block"] or modules["algo_candle"])
    cycle_ok = amd.get("phase") in {"ACCUMULATION", "MANIPULATION", "DISTRIBUTION", "TRANSITION"}
    pd_ok = modules["premium_discount_alignment"]
    mtf_ok = htf_direction == ("BULLISH" if direction == "BUY" else "BEARISH") or not htf_rows
    fake_ok = not fake.get("valid") or fake.get("direction") != ("BULLISH" if direction == "BUY" else "BEARISH")

    score = 0
    score += 20 if liquidity_ok else 0
    score += 15 if shift_ok else 0
    score += 15 if poi_ok else 0
    score += 15 if confirmation_ok else 0
    score += 10 if cycle_ok else 0
    score += 10 if pd_ok else 0
    score += 10 if mtf_ok else 0
    score += 5 if fake_ok else 0

    target1, target2 = _nearest_target(liquidity, direction, price, atr)
    if direction == "BUY":
        base_low = min(_f(c, "low") for c in selected[-10:])
        if sweep.get("valid") and sweep.get("side") == "SELL_SIDE":
            base_low = min(base_low, float(sweep.get("level")))
        sl = base_low - atr * 0.15
        risk = max(price - sl, atr * 0.7)
        tp1 = target1 if target1 and target1 > price else price + risk * 2.0
        tp2 = target2 if target2 and target2 > tp1 else price + risk * 3.0
        rr = (tp1 - price) / risk
    else:
        base_high = max(_f(c, "high") for c in selected[-10:])
        if sweep.get("valid") and sweep.get("side") == "BUY_SIDE":
            base_high = max(base_high, float(sweep.get("level")))
        sl = base_high + atr * 0.15
        risk = max(sl - price, atr * 0.7)
        tp1 = target1 if target1 and target1 < price else price - risk * 2.0
        tp2 = target2 if target2 and target2 < tp1 else price - risk * 3.0
        rr = (price - tp1) / risk

    hard_ready = all([liquidity_ok, shift_ok, poi_ok, confirmation_ok, mtf_ok, fake_ok, rr >= 1.40])
    signal = direction if hard_ready and score >= 70 else "WAIT"

    money_transfer = "BUY_SIDE_DELIVERY" if sweep.get("side") == "SELL_SIDE" and direction == "BUY" else "SELL_SIDE_DELIVERY" if sweep.get("side") == "BUY_SIDE" and direction == "SELL" else "NONE"
    strong_trend = bool(sweep.get("valid") and shift_ok and modules["displacement"])

    reason_parts = [
        f"{amd.get('phase')} cycle",
        f"{direction} local structure",
        f"HTF={htf_direction}",
    ]
    if sweep.get("valid"):
        reason_parts.append(f"{sweep.get('side')} liquidity sweep")
    if money_transfer != "NONE":
        reason_parts.append(money_transfer)
    if fvg.get("valid"):
        reason_parts.append(f"{fvg.get('type')} FVG")
    if modules["algo_candle"]:
        reason_parts.append("Algo Candle")
    if modules["previous_candle_liquidity"]:
        reason_parts.append("previous-candle liquidity")
    if modules.get("order_block"):
        reason_parts.append("Order Block")
    if modules.get("breaker_retest"):
        reason_parts.append("Breaker Retest")
    if modules.get("rejection_block"):
        reason_parts.append("Rejection Block")
    if modules.get("hvi"):
        reason_parts.append("HVI")
    if modules["ping_pong"]:
        reason_parts.append("Ping Pong")
    if fake.get("valid") and not fake_ok:
        reason_parts.append("fake structure break risk")
    if not hard_ready:
        reason_parts.append("hard validation incomplete")

    checks = {
        "major_liquidity": liquidity_ok,
        "liquidity_sweep": bool(sweep.get("valid")),
        "money_transfer": money_transfer != "NONE",
        "structure_bos_choch": bool(structure.get("bos") != "NONE" or structure.get("choch") != "NONE"),
        "strong_high_low_context": bool(structure.get("strong_high") or structure.get("strong_low")),
        "fake_bms_filter": fake_ok,
        "amd_cycle": cycle_ok,
        "premium_discount": pd_ok,
        "fvg": bool(fvg.get("valid")),
        "algo_candle": modules["algo_candle"],
        "displacement": modules["displacement"],
        "order_block": modules.get("order_block",False),
        "breaker_retest": modules.get("breaker_retest",False),
        "rejection_block": modules.get("rejection_block",False),
        "hvi": modules.get("hvi",False),
        "previous_candle_liquidity": modules["previous_candle_liquidity"],
        "bos_choch_confirmation": modules["bos_choch_confirmation"],
        "engulfing_confirmation": modules["engulfing_confirmation"],
        "ping_pong": modules["ping_pong"],
        "mtf_alignment": mtf_ok,
        "rr_ok": rr >= 1.40,
        "hard_deterministic_gate": hard_ready,
    }

    return {
        "signal": signal,
        "raw_direction": direction,
        "state": "READY_FOR_AI" if hard_ready else "WAIT_VALIDATION",
        "setup": "ALGO_SMC",
        "score": int(score),
        "confidence": int(score),
        "entry": round(price, 5),
        "stop_loss": round(sl, 5),
        "take_profit": [round(tp1, 5), round(tp2, 5)],
        "risk_reward": round(rr, 2),
        "reason": " · ".join(reason_parts),
        "checks": checks,
        "structure": structure,
        "liquidity": liquidity,
        "sweep": sweep,
        "amd": amd,
        "premium_discount": premium,
        "fvg": fvg,
        "order_block": order_block,
        "breaker_block": breaker_block,
        "rejection_block": rejection_block,
        "hvi": hvi,
        "displacement": displacement,
        "fake_break": fake,
        "money_transfer": money_transfer,
        "strong_trend": strong_trend,
        "weekly_cycle": weekly_cycle,
        "cycle_90m": cycle_90m,
        "entry_modules": modules,
        "current_price": round(price, 5),
        "selected_interval": selected_interval,
        "book_basis": [
            "Liquidity / Daily Cycle / HTF Cycle",
            "Money Transfer",
            "Algo Market Structure",
            "Premium / Discount",
            "Efficient / Inefficient Price Action",
            "Order Block / Breaker Block / Rejection Block concepts",
            "Top Down Analysis",
            "Ping Pong Mastery",
        ],
    }
