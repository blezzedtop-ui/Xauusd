from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import math


@dataclass
class Swing:
    index: int
    price: float


@dataclass
class Zone:
    kind: str
    low: float
    high: float
    index: int
    source: str
    valid: bool = True

    @property
    def level(self) -> float:
        return (self.low + self.high) / 2.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "low": round(self.low, 5),
            "high": round(self.high, 5),
            "level": round(self.level, 5),
            "index": self.index,
            "source": self.source,
            "valid": self.valid,
        }


def _f(c: dict[str, Any], key: str) -> float:
    return float(c[key])


def _body(c: dict[str, Any]) -> tuple[float, float]:
    return min(_f(c, "open"), _f(c, "close")), max(_f(c, "open"), _f(c, "close"))


def _atr(candles: list[dict[str, Any]], n: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    trs: list[float] = []
    for i in range(max(1, len(candles) - n), len(candles)):
        c, p = candles[i], candles[i - 1]
        trs.append(max(
            _f(c, "high") - _f(c, "low"),
            abs(_f(c, "high") - _f(p, "close")),
            abs(_f(c, "low") - _f(p, "close")),
        ))
    return sum(trs) / max(1, len(trs))


def _swings(candles: list[dict[str, Any]], left: int = 2, right: int = 2) -> tuple[list[Swing], list[Swing]]:
    highs: list[Swing] = []
    lows: list[Swing] = []
    for i in range(left, len(candles) - right):
        hi = _f(candles[i], "high")
        lo = _f(candles[i], "low")
        if hi >= max(_f(candles[j], "high") for j in range(i - left, i + right + 1)):
            highs.append(Swing(i, hi))
        if lo <= min(_f(candles[j], "low") for j in range(i - left, i + right + 1)):
            lows.append(Swing(i, lo))
    return highs, lows


def _trend(candles: list[dict[str, Any]]) -> str:
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
        a = _f(candles[-1], "close")
        b = sum(_f(c, "close") for c in candles[-11:-1]) / 10.0
        if a > b * 1.0006:
            return "BULLISH"
        if a < b * 0.9994:
            return "BEARISH"
    return "NEUTRAL"


def _structure(candles: list[dict[str, Any]]) -> dict[str, Any]:
    highs, lows = _swings(candles)
    prev_high = highs[-2] if len(highs) >= 2 else None
    last_high = highs[-1] if highs else None
    prev_low = lows[-2] if len(lows) >= 2 else None
    last_low = lows[-1] if lows else None
    price = _f(candles[-1], "close")
    tr = _trend(candles)

    bos = None
    bos_level = None
    bos_index = None
    if last_high and price > last_high.price:
        bos = "BULLISH"
        bos_level = last_high.price
        bos_index = len(candles) - 1
    elif last_low and price < last_low.price:
        bos = "BEARISH"
        bos_level = last_low.price
        bos_index = len(candles) - 1

    choch = None
    choch_level = None
    if tr == "BULLISH" and last_low and price < last_low.price:
        choch = "BEARISH"
        choch_level = last_low.price
    elif tr == "BEARISH" and last_high and price > last_high.price:
        choch = "BULLISH"
        choch_level = last_high.price

    return {
        "trend": tr,
        "swing_highs": [{"index": x.index, "price": round(x.price, 5)} for x in highs[-6:]],
        "swing_lows": [{"index": x.index, "price": round(x.price, 5)} for x in lows[-6:]],
        "last_high": last_high.price if last_high else None,
        "last_low": last_low.price if last_low else None,
        "bos": bos,
        "bos_level": bos_level,
        "bos_index": bos_index,
        "choch": choch,
        "choch_level": choch_level,
    }


def _equal_levels(points: list[Swing], atr: float, side: str) -> dict[str, Any]:
    if len(points) < 2:
        return {"valid": False, "side": side, "level": None, "indices": []}
    tol = max(atr * 0.35, abs(points[-1].price) * 0.00025)
    for i in range(len(points) - 2, -1, -1):
        a, b = points[i], points[-1]
        if abs(a.price - b.price) <= tol:
            return {"valid": True, "side": side, "level": round((a.price + b.price) / 2, 5), "indices": [a.index, b.index], "tolerance": round(tol, 5)}
    return {"valid": False, "side": side, "level": None, "indices": [], "tolerance": round(tol, 5)}


def _liquidity(candles: list[dict[str, Any]]) -> dict[str, Any]:
    atr = max(_atr(candles), _f(candles[-1], "close") * 0.00015)
    highs, lows = _swings(candles[:-1]) if len(candles) > 6 else ([], [])
    eqh = _equal_levels(highs, atr, "EQH")
    eql = _equal_levels(lows, atr, "EQL")

    # Prior-candle liquidity is explicitly used as an entry model in the source.
    prev = candles[-2]
    cur = candles[-1]
    prev_high, prev_low = _f(prev, "high"), _f(prev, "low")
    prev_buy_side = _f(cur, "high") > prev_high and _f(cur, "close") < prev_high
    prev_sell_side = _f(cur, "low") < prev_low and _f(cur, "close") > prev_low

    sweep = {"valid": False, "type": "NONE", "level": None}
    if prev_sell_side:
        sweep = {"valid": True, "type": "SELL_SIDE_SWEEP", "level": prev_low}
    elif prev_buy_side:
        sweep = {"valid": True, "type": "BUY_SIDE_SWEEP", "level": prev_high}
    else:
        # Look for sweep of an equal-liquidity level on the latest few candles.
        for c in reversed(candles[-6:]):
            if eqh.get("valid") and _f(c, "high") > float(eqh["level"]) + atr * 0.05 and _f(c, "close") < float(eqh["level"]):
                sweep = {"valid": True, "type": "BUY_SIDE_SWEEP", "level": eqh["level"]}
                break
            if eql.get("valid") and _f(c, "low") < float(eql["level"]) - atr * 0.05 and _f(c, "close") > float(eql["level"]):
                sweep = {"valid": True, "type": "SELL_SIDE_SWEEP", "level": eql["level"]}
                break

    # Session liquidity is implemented as a configurable rolling proxy. The book
    # explicitly studies session liquidity, but does not give universal clock rules.
    lookback = min(24, len(candles) - 1)
    session_high = max(_f(c, "high") for c in candles[-lookback-1:-1]) if lookback > 2 else prev_high
    session_low = min(_f(c, "low") for c in candles[-lookback-1:-1]) if lookback > 2 else prev_low
    return {
        "eqh": eqh,
        "eql": eql,
        "previous_candle_high": prev_high,
        "previous_candle_low": prev_low,
        "previous_candle_sweep": sweep,
        "session_high_proxy": session_high,
        "session_low_proxy": session_low,
    }


def _fvg(candles: list[dict[str, Any]]) -> dict[str, Any]:
    for i in range(len(candles) - 3, max(1, len(candles) - 12), -1):
        a, _, c = candles[i - 1], candles[i], candles[i + 1]
        if _f(c, "low") > _f(a, "high"):
            return {"valid": True, "type": "BULLISH_FVG", "low": _f(a, "high"), "high": _f(c, "low"), "index": i}
        if _f(c, "high") < _f(a, "low"):
            return {"valid": True, "type": "BEARISH_FVG", "low": _f(c, "high"), "high": _f(a, "low"), "index": i}
    return {"valid": False, "type": "NONE", "low": None, "high": None, "index": None}


def _order_block(candles: list[dict[str, Any]], direction: str, structure: dict[str, Any]) -> dict[str, Any]:
    if len(candles) < 8:
        return {"valid": False, "type": "NONE", "low": None, "high": None, "index": None}
    bos_idx = structure.get("bos_index")
    start = max(1, len(candles) - 30)
    end = bos_idx if isinstance(bos_idx, int) else len(candles) - 1
    if direction == "BUY":
        for i in range(end - 1, start - 1, -1):
            if _f(candles[i], "close") < _f(candles[i], "open"):
                lo, hi = _body(candles[i])
                return {"valid": True, "type": "BULLISH_ORDER_BLOCK", "low": lo, "high": hi, "index": i}
    elif direction == "SELL":
        for i in range(end - 1, start - 1, -1):
            if _f(candles[i], "close") > _f(candles[i], "open"):
                lo, hi = _body(candles[i])
                return {"valid": True, "type": "BEARISH_ORDER_BLOCK", "low": lo, "high": hi, "index": i}
    return {"valid": False, "type": "NONE", "low": None, "high": None, "index": None}


def _zone_touch(candles: list[dict[str, Any]], zone: dict[str, Any] | None, direction: str, atr: float) -> dict[str, Any]:
    if not zone or not zone.get("valid"):
        return {"valid": False, "index": None, "rejection": False}
    low, high = float(zone["low"]), float(zone["high"])
    for i in range(len(candles) - 1, max(0, len(candles) - 5), -1):
        c = candles[i]
        touched = _f(c, "low") <= high + atr * 0.15 and _f(c, "high") >= low - atr * 0.15
        if not touched:
            continue
        if direction == "BUY":
            rejected = _f(c, "close") > _f(c, "open") and _f(c, "close") >= low
        else:
            rejected = _f(c, "close") < _f(c, "open") and _f(c, "close") <= high
        return {"valid": True, "index": i, "rejection": rejected, "candle_time": c.get("time")}
    return {"valid": False, "index": None, "rejection": False}


def _id_activation(candles: list[dict[str, Any]], direction: str, liquidity: dict[str, Any], structure: dict[str, Any]) -> dict[str, Any]:
    # IDM is treated as a liquidity/structure inducement before the directional break.
    sweep = liquidity.get("previous_candle_sweep") or {}
    if sweep.get("valid"):
        return {"valid": True, "type": "PREVIOUS_CANDLE_LIQUIDITY_IDM", "level": sweep.get("level")}
    highs, lows = _swings(candles[:-2]) if len(candles) > 8 else ([], [])
    if direction == "BUY" and lows and structure.get("bos") == "BULLISH":
        return {"valid": True, "type": "IDM_BEFORE_BOS", "level": lows[-1].price}
    if direction == "SELL" and highs and structure.get("bos") == "BEARISH":
        return {"valid": True, "type": "IDM_BEFORE_BOS", "level": highs[-1].price}
    return {"valid": False, "type": "NONE", "level": None}


def _entry_modules(candles: list[dict[str, Any]], direction: str, structure: dict[str, Any], liquidity: dict[str, Any], ob: dict[str, Any], fvg: dict[str, Any]) -> dict[str, Any]:
    last = candles[-1]
    prev = candles[-2]
    body_lo, body_hi = _body(last)
    prev_lo, prev_hi = _body(prev)
    engulf_buy = _f(last, "close") > _f(last, "open") and _f(prev, "close") < _f(prev, "open") and body_lo <= prev_lo and body_hi >= prev_hi
    engulf_sell = _f(last, "close") < _f(last, "open") and _f(prev, "close") > _f(prev, "open") and body_lo <= prev_lo and body_hi >= prev_hi
    engulf = engulf_buy if direction == "BUY" else engulf_sell

    bos_or_choch = structure.get("bos") == direction or structure.get("choch") == direction
    flip = False
    if ob.get("valid"):
        low, high = float(ob["low"]), float(ob["high"])
        flip = (_f(last, "close") > high if direction == "BUY" else _f(last, "close") < low)

    prev_sweep = liquidity.get("previous_candle_sweep") or {}
    prev_sweep_direction = (prev_sweep.get("type") == "SELL_SIDE_SWEEP" and direction == "BUY") or (prev_sweep.get("type") == "BUY_SIDE_SWEEP" and direction == "SELL")

    single_candle = False
    if direction == "BUY":
        single_candle = _f(last, "low") < _f(prev, "low") and _f(last, "close") > _f(prev, "high") * 0.99985
    else:
        single_candle = _f(last, "high") > _f(prev, "high") and _f(last, "close") < _f(prev, "low") * 1.00015

    if direction == "BUY":
        fvg_match = fvg.get("valid") and fvg.get("type") == "BULLISH_FVG"
        ob_match = ob.get("valid") and ob.get("type") == "BULLISH_ORDER_BLOCK"
    else:
        fvg_match = fvg.get("valid") and fvg.get("type") == "BEARISH_FVG"
        ob_match = ob.get("valid") and ob.get("type") == "BEARISH_ORDER_BLOCK"

    modules = {
        "idm_choch": bool(structure.get("choch") == direction and (engulf or prev_sweep_direction or flip)),
        "idm_flip": bool(flip and (structure.get("bos") == direction or prev_sweep_direction)),
        "previous_candle_liquidity": bool(prev_sweep_direction),
        "single_candle_liquidity_check": bool(single_candle and prev_sweep_direction),
        "engulfing_confirmation": bool(engulf),
        "ob_confirmation": bool(ob_match),
        "fvg_confirmation": bool(fvg_match),
        "bos_or_choch": bool(bos_or_choch),
    }
    return modules


def _nearest_opposing(candles: list[dict[str, Any]], direction: str, price: float) -> float | None:
    highs, lows = _swings(candles)
    if direction == "BUY":
        vals = [x.price for x in highs if x.price > price]
        return min(vals) if vals else None
    vals = [x.price for x in lows if x.price < price]
    return max(vals) if vals else None


def analyze_smc(candles: list[dict[str, Any]], mtf: dict[str, Any] | None = None, selected_interval: str = "5min") -> dict[str, Any]:
    if len(candles) < 60:
        return {
            "signal": "WAIT", "raw_direction": "WAIT", "score": 0, "confidence": 0,
            "state": "INSUFFICIENT_DATA", "setup": "WAIT", "reason": "SMC uchun yetarli candle mavjud emas.",
            "checks": {}, "entry": None, "stop_loss": None, "take_profit": [], "risk_reward": None,
        }

    price = _f(candles[-1], "close")
    atr = max(_atr(candles), price * 0.0002)
    structure = _structure(candles)
    liquidity = _liquidity(candles)
    direction = structure.get("trend") if structure.get("trend") in {"BULLISH", "BEARISH"} else "WAIT"
    if structure.get("choch") in {"BUY", "SELL"}:
        direction = structure["choch"]

    if direction == "WAIT":
        return {
            "signal": "WAIT", "raw_direction": "WAIT", "score": 0, "confidence": 0,
            "state": "WAIT_STRUCTURE", "setup": "WAIT_STRUCTURE",
            "reason": "Aniq SMC directional structure hali aniqlanmadi.", "checks": {"structure": False},
            "entry": None, "stop_loss": None, "take_profit": [], "risk_reward": None,
            "structure": structure, "liquidity": liquidity, "atr": round(atr, 5), "price": round(price, 5),
        }

    ob = _order_block(candles, direction, structure)
    fvg = _fvg(candles)
    idm = _id_activation(candles, direction, liquidity, structure)
    ob_touch = _zone_touch(candles, ob, direction, atr)
    fvg_touch = _zone_touch(candles, fvg, direction, atr)
    modules = _entry_modules(candles, direction, structure, liquidity, ob, fvg)

    mtf_bias = str((mtf or {}).get("direction_bias") or "NEUTRAL")
    mtf_match = mtf_bias == direction
    structure_ok = bool(structure.get("bos") == direction or structure.get("choch") == direction)
    liquidity_ok = bool((liquidity.get("previous_candle_sweep") or {}).get("valid") or liquidity.get("eqh", {}).get("valid") or liquidity.get("eql", {}).get("valid"))
    poi_ok = bool(ob.get("valid") or fvg.get("valid"))
    entry_ok = bool(
        modules.get("idm_choch") or modules.get("idm_flip") or modules.get("previous_candle_liquidity")
        or modules.get("single_candle_liquidity_check") or modules.get("engulfing_confirmation")
    )

    # Implementation score: 25 structure + 20 liquidity + 20 POI + 20 entry module + 15 MTF.
    score = (25 if structure_ok else 0) + (20 if liquidity_ok else 0) + (20 if poi_ok else 0) + (20 if entry_ok else 0) + (15 if mtf_match else 0)
    if not mtf_match:
        score = max(0, score - 15)

    recent_hi = max(_f(c, "high") for c in candles[-12:])
    recent_lo = min(_f(c, "low") for c in candles[-12:])
    if direction == "BUY":
        structural_low = min(recent_lo, float(ob["low"]) if ob.get("valid") else recent_lo)
        sl = structural_low - atr * 0.15
        risk = max(price - sl, atr * 0.6)
        target = _nearest_opposing(candles, direction, price)
        tp1 = target if target and (target - price) / risk >= 1.5 else price + risk * 2.0
        tp2 = price + risk * 3.0
        rr = (tp1 - price) / risk
    else:
        structural_high = max(recent_hi, float(ob["high"]) if ob.get("valid") else recent_hi)
        sl = structural_high + atr * 0.15
        risk = max(sl - price, atr * 0.6)
        target = _nearest_opposing(candles, direction, price)
        tp1 = target if target and (price - target) / risk >= 1.5 else price - risk * 2.0
        tp2 = price - risk * 3.0
        rr = (price - tp1) / risk

    checks = {
        "structure_bos_choch": structure_ok,
        "liquidity": liquidity_ok,
        "eqh_or_eql": bool(liquidity.get("eqh", {}).get("valid") or liquidity.get("eql", {}).get("valid")),
        "liquidity_sweep": bool((liquidity.get("previous_candle_sweep") or {}).get("valid")),
        "session_liquidity_proxy": bool(liquidity.get("session_high_proxy") and liquidity.get("session_low_proxy")),
        "inducement_idm": bool(idm.get("valid")),
        "order_block": bool(ob.get("valid")),
        "fvg": bool(fvg.get("valid")),
        "poi": poi_ok,
        "ob_touch": bool(ob_touch.get("valid")),
        "fvg_touch": bool(fvg_touch.get("valid")),
        "entry_module": entry_ok,
        "idm_choch": modules.get("idm_choch", False),
        "idm_flip": modules.get("idm_flip", False),
        "previous_candle_liquidity": modules.get("previous_candle_liquidity", False),
        "single_candle_liquidity_check": modules.get("single_candle_liquidity_check", False),
        "engulfing_confirmation": modules.get("engulfing_confirmation", False),
        "mtf_match": mtf_match,
        "rr_ok": rr >= 1.40,
    }

    critical = structure_ok and entry_ok and mtf_match and rr >= 1.40
    confirmed = bool(critical and score >= 70)
    signal = direction if confirmed else "WAIT"

    reasons: list[str] = []
    if structure_ok: reasons.append(f"{structure.get('bos') or structure.get('choch')} structure")
    if liquidity.get("eqh", {}).get("valid"): reasons.append("EQH liquidity")
    if liquidity.get("eql", {}).get("valid"): reasons.append("EQL liquidity")
    if (liquidity.get("previous_candle_sweep") or {}).get("valid"): reasons.append(liquidity["previous_candle_sweep"].get("type", "liquidity sweep"))
    if idm.get("valid"): reasons.append(idm.get("type", "IDM"))
    if ob.get("valid"): reasons.append(ob.get("type", "Order Block"))
    if fvg.get("valid"): reasons.append(fvg.get("type", "FVG"))
    if modules.get("idm_choch"): reasons.append("IDM + CHoCH")
    if modules.get("idm_flip"): reasons.append("IDM + FLIP")
    if modules.get("previous_candle_liquidity"): reasons.append("previous-candle liquidity")
    if modules.get("single_candle_liquidity_check"): reasons.append("single-candle liquidity check")
    if modules.get("engulfing_confirmation"): reasons.append("candle confirmation")
    if not mtf_match: reasons.append(f"MTF conflict: {mtf_bias}")
    if not rr >= 1.40: reasons.append("RR below SignalX minimum 1.40")
    if not confirmed: reasons.append("NO VALIDATION, NO TRADE")

    return {
        "signal": signal,
        "raw_direction": direction,
        "score": int(min(100, max(0, score))),
        "confidence": int(min(99, max(20, score))),
        "state": "CONFIRMED" if confirmed else "WAIT_VALIDATION",
        "setup": "SMC_AI_CONFIRMATION" if confirmed else "WAIT_VALIDATION",
        "reason": "; ".join(dict.fromkeys(reasons)) or "SMC setup incomplete.",
        "checks": checks,
        "entry": round(price, 5) if confirmed else None,
        "stop_loss": round(sl, 5) if confirmed else None,
        "take_profit": [round(tp1, 5), round(tp2, 5)] if confirmed else [],
        "risk_reward": round(rr, 2),
        "structure": structure,
        "liquidity": liquidity,
        "idm": idm,
        "order_block": ob,
        "fvg": fvg,
        "entry_modules": modules,
        "poi_touches": {"order_block": ob_touch, "fvg": fvg_touch},
        "atr": round(atr, 5),
        "price": round(price, 5),
        "selected_interval": selected_interval,
    }


def summarize_smc_mtf(timeframes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    order = ["1day", "4h", "1h", "30min", "15min", "5min", "1min"]
    labels = {"1day": "Daily", "4h": "H4", "1h": "H1", "30min": "M30", "15min": "M15", "5min": "M5", "1min": "M1"}
    rows: list[dict[str, Any]] = []
    for tf in order:
        x = timeframes.get(tf) or {}
        rows.append({"interval": tf, "label": labels[tf], "trend": x.get("trend", "NEUTRAL"), "bos": x.get("bos"), "choch": x.get("choch"), "price": x.get("price")})
    dirs = [r["trend"] for r in rows if r["trend"] in {"BULLISH", "BEARISH"}]
    bull, bear = dirs.count("BULLISH"), dirs.count("BEARISH")
    bias = "BULLISH" if bull > bear and bull >= 3 else "BEARISH" if bear > bull and bear >= 3 else "NEUTRAL"
    alignment = (bull >= 4 if bias == "BULLISH" else bear >= 4 if bias == "BEARISH" else False)
    return {"rows": rows, "direction_bias": bias, "alignment": alignment, "bullish_count": bull, "bearish_count": bear}
