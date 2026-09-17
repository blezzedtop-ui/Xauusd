"""SignalX additive AlgoTrade strategy.

This module is intentionally isolated from the existing strategy/AutoTrade
engine. It consumes the same TradingView candle pipeline and exposes a read-
only analysis endpoint. It does not enqueue MT5 orders.
"""
from __future__ import annotations
import json

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

import main as core

router = APIRouter(prefix="/api/v1/algotrade", tags=["AlgoTrade"])

ALGO_TIMEFRAMES = ("4h", "1h", "15min", "5min")


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _direction_from_trend(trend: str) -> str:
    t = str(trend or "").upper()
    if t == "BULLISH":
        return "BUY"
    if t == "BEARISH":
        return "SELL"
    return "WAIT"


def _in_zone(price: float, zone: dict[str, Any] | None) -> bool:
    if not isinstance(zone, dict):
        return False
    lo, hi = _num(zone.get("low"), float("nan")), _num(zone.get("high"), float("nan"))
    return lo == lo and hi == hi and min(lo, hi) <= price <= max(lo, hi)


def _component_signal(component: Any) -> str:
    if isinstance(component, dict):
        for key in ("signal", "type", "confirmation"):
            value = str(component.get(key) or "").upper()
            if value in {"BUY", "SELL", "BULLISH", "BEARISH"}:
                return "BUY" if value in {"BUY", "BULLISH"} else "SELL"
    value = str(component or "").upper()
    if value in {"BUY", "BULLISH"}:
        return "BUY"
    if value in {"SELL", "BEARISH"}:
        return "SELL"
    return "WAIT"


def _score_component(expected: str, actual: str) -> int:
    return 1 if expected in {"BUY", "SELL"} and actual == expected else 0


def _algo_for_timeframe(candles: list[dict[str, Any]], tf: str) -> dict[str, Any]:
    if len(candles) < 40:
        return {"signal": "WAIT", "confidence": 0, "score": 0, "reason": "Yetarli candle ma'lumoti yo'q", "interval": tf}

    trend = core.timeframe_trend(candles)
    structure = core._structure_state(candles)
    highs, lows = core._swing_points(candles)
    atr_value = max(_num(core.atr(candles)), 0.0001)
    fvg = core._detect_fvg(candles)
    ob = core._detect_order_block(candles, atr_value)
    liq = core._detect_liquidity(candles, highs, lows)
    snr = core._snr_zone_analysis(candles)
    price = _num(candles[-1].get("close"))

    trend_dir = _direction_from_trend(trend.get("trend"))
    structure_dir = "BUY" if structure.get("bos") == "BULLISH" or structure.get("choch") == "BULLISH" else "SELL" if structure.get("bos") == "BEARISH" or structure.get("choch") == "BEARISH" else "WAIT"
    liq_dir = "SELL" if liq.get("type") == "BUY_SIDE_SWEEP" else "BUY" if liq.get("type") == "SELL_SIDE_SWEEP" else "WAIT"
    ob_dir = _component_signal(ob)
    fvg_dir = _component_signal(fvg)
    snr_dir = _component_signal(snr)

    # Direction is deliberately conservative: trend + structure must agree.
    direction = trend_dir if trend_dir == structure_dir else "WAIT"
    if direction == "WAIT":
        # A fresh liquidity sweep can create the reversal confirmation, but it
        # still requires an aligned OB/FVG component.
        for candidate in (liq_dir, ob_dir, fvg_dir):
            if candidate in {"BUY", "SELL"} and candidate == ob_dir == fvg_dir:
                direction = candidate
                break

    checks = {
        "trend": _score_component(direction, trend_dir),
        "structure": _score_component(direction, structure_dir),
        "liquidity": _score_component(direction, liq_dir),
        "order_block": _score_component(direction, ob_dir),
        "fvg": _score_component(direction, fvg_dir),
        "snr": _score_component(direction, snr_dir),
    }
    confidence = round(100 * sum(checks.values()) / len(checks)) if direction != "WAIT" else 0

    return {
        "interval": tf,
        "signal": direction,
        "confidence": confidence,
        "score": confidence,
        "trend": trend.get("trend", "NEUTRAL"),
        "rsi": trend.get("rsi"),
        "current_price": price,
        "structure": structure,
        "liquidity": liq,
        "order_block": ob,
        "fvg": fvg,
        "snr": snr,
        "checks": checks,
        "candle_time": candles[-1].get("time"),
        "atr": atr_value,
    }


def _build_trade_levels(direction: str, price: float, atr_value: float, m15: dict[str, Any], m5: dict[str, Any]) -> tuple[float | None, float | None, list[float], float]:
    if direction not in {"BUY", "SELL"} or price <= 0:
        return None, None, [], 0.0

    ref = m5 if m5.get("signal") == direction else m15
    structure = ref.get("structure") or {}
    if direction == "BUY":
        sl = _num(structure.get("swing_low"), price - atr_value * 1.2)
        if sl >= price:
            sl = price - atr_value * 1.2
        risk = max(price - sl, atr_value * 0.5)
        tp = [price + risk * 2.0, price + risk * 3.0]
    else:
        sl = _num(structure.get("swing_high"), price + atr_value * 1.2)
        if sl <= price:
            sl = price + atr_value * 1.2
        risk = max(sl - price, atr_value * 0.5)
        tp = [price - risk * 2.0, price - risk * 3.0]
    rr = abs((tp[0] - price) / max(abs(price - sl), 1e-9))
    return round(price, 4), round(sl, 4), [round(x, 4) for x in tp], round(rr, 2)


async def build_algotrade(symbol: str = "XAU/USD") -> dict[str, Any]:
    symbol = core.clean_symbol(symbol)
    data: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for tf in ALGO_TIMEFRAMES:
        try:
            candles, mode, warning = await core.get_candles(symbol, tf, 180)
            item = _algo_for_timeframe(candles, tf)
            item["mode"] = mode
            item["warning"] = warning
            data[tf] = item
        except Exception as exc:
            errors[tf] = f"{type(exc).__name__}: {exc}"
            data[tf] = {"interval": tf, "signal": "UNAVAILABLE", "confidence": 0, "score": 0, "reason": str(exc)}

    h4 = data.get("4h", {})
    h1 = data.get("1h", {})
    m15 = data.get("15min", {})
    m5 = data.get("5min", {})
    h4_sig, h1_sig = h4.get("signal", "WAIT"), h1.get("signal", "WAIT")

    mtf_match = h4_sig in {"BUY", "SELL"} and h4_sig == h1_sig
    direction = h4_sig if mtf_match else "WAIT"
    m15_ok = m15.get("signal") == direction
    m5_ok = m5.get("signal") == direction

    # Use the most recent available ATR for level sizing without modifying any
    # existing strategy output.
    atr_value = max(_num(m5.get("atr")) or _num(m15.get("atr")), 0.01)
    price = _num(m5.get("current_price")) or _num(m15.get("current_price"))
    entry, sl, tp, rr = _build_trade_levels(direction if (m15_ok and m5_ok) else "WAIT", price, atr_value, m15, m5)

    score = 0
    score += 20 if mtf_match else 0
    score += 15 if h1_sig == direction and direction in {"BUY", "SELL"} else 0
    score += 15 if m15_ok else 0
    score += 5 if m5_ok else 0
    liq = m15.get("liquidity") or {}
    ob = m15.get("order_block") or {}
    fvg = m15.get("fvg") or {}
    score += 15 if _component_signal(liq) == direction else 0
    score += 10 if _component_signal(ob) == direction else 0
    score += 10 if _component_signal(fvg) == direction else 0
    score += 5 if _component_signal(m15.get("snr")) == direction else 0
    score += 5 if rr >= 2.0 else 0

    final = direction if score >= 85 and mtf_match and m15_ok and m5_ok and rr >= 2.0 else "WAIT"

    # Server-side execution candidates are produced only after the complete
    # AlgoTrade MTF gate is confirmed.  Each supported timeframe gets its own
    # structure-based levels so AutoTrade can execute on M5/H1/H4/M15 without
    # reusing a stale level from another timeframe. M1 is never part of this set.
    execution_candidates: dict[str, dict[str, Any]] = {}
    if final in {"BUY", "SELL"}:
        for tf in ALGO_TIMEFRAMES:
            item = data.get(tf) or {}
            if item.get("signal") != final:
                continue
            tf_price = _num(item.get("current_price")) or price
            tf_atr = max(_num(item.get("atr")), 0.01)
            e, s, tps, tf_rr = _build_trade_levels(final, tf_price, tf_atr, item, item)
            if e is None or s is None or len(tps) < 1 or tf_rr < 2.0:
                continue
            execution_candidates[tf] = {
                "interval": tf,
                "signal": final,
                "confidence": float(item.get("confidence") or 0),
                "entry": e,
                "stop_loss": s,
                "take_profit": tps,
                "risk_reward": tf_rr,
                "candle_time": item.get("candle_time"),
                "strategy_engine": "XAUUSD MTF ICT Confirmation",
                "strategy_version": "ALGOTRADE_V1",
                "mtf_confirmed": True,
            }

    reasons = []
    reasons.append("H4 + H1 MTF mos" if mtf_match else "H4/H1 MTF mos emas")
    reasons.append("M15 tasdiq" if m15_ok else "M15 tasdiq yo'q")
    reasons.append("M5 entry tasdiq" if m5_ok else "M5 entry tasdiq yo'q")
    reasons.append("Liquidity Sweep" if _component_signal(liq) == direction and direction != "WAIT" else "Liquidity Sweep yo'q")
    reasons.append("Order Block" if _component_signal(ob) == direction and direction != "WAIT" else "Order Block mos emas")
    reasons.append("FVG" if _component_signal(fvg) == direction and direction != "WAIT" else "FVG mos emas")
    reasons.append(f"RR 1:{rr:.2f}" if rr else "RR hisoblanmadi")

    return {
        "ok": True,
        "symbol": symbol,
        "strategy": "XAUUSD MTF ICT Confirmation",
        "version": "ALGOTRADE_V1",
        "signal": final,
        "candidate_direction": direction,
        "score": min(score, 100),
        "confidence": min(score, 100) if final != "WAIT" else score,
        "entry": entry if final != "WAIT" else None,
        "stop_loss": sl if final != "WAIT" else None,
        "take_profit": tp if final != "WAIT" else [],
        "risk_reward": rr,
        "timeframes": data,
        "execution_candidates": execution_candidates,
        "rules": {
            "h4_trend": "Higher High/Low yoki Lower High/Low orqali bias",
            "h1_confirmation": "H4 bilan bir tomonda bo'lishi shart",
            "m15_setup": "Liquidity Sweep + OB/FVG + BOS/CHoCH",
            "m5_entry": "Structure confirmation + retest",
            "minimum_rr": 2.0,
            "auto_trade": "ELIGIBLE_VIA_HISTORY_AUTOTRADE_PIPELINE",
        },
        "checks": {
            "mtf_match": mtf_match,
            "m15_confirmation": m15_ok,
            "m5_confirmation": m5_ok,
            "rr_ge_2": rr >= 2.0,
            "score_ge_85": score >= 85,
        },
        "reason": "; ".join(reasons),
        "errors": errors,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "execution_note": "AlgoTrade V1 server-side tasdiqlangan execution_candidates orqali mavjud MT5 AutoTrade queue bilan ishlashi mumkin; M1 har doim bloklangan.",
    }


@router.get("/XAU/USD")
async def algotrade_xauusd(authorization: str | None = Header(default=None), session: Session = Depends(core.db)) -> dict[str, Any]:
    user = core.require_admin(authorization, session)
    result = await build_algotrade("XAU/USD")
    if result.get("signal") in {"BUY", "SELL"}:
        for tf, item in (result.get("execution_candidates") or {}).items():
            if item.get("signal") not in {"BUY", "SELL"}:
                continue
            candle = str(item.get("candle_time") or "")
            exists = session.scalar(core.select(core.SignalHistory).where(
                core.SignalHistory.user_id == user.id, core.SignalHistory.source == "AlgoTrade",
                core.SignalHistory.symbol == "XAU/USD", core.SignalHistory.interval == tf,
                core.SignalHistory.candle_time == candle, core.SignalHistory.direction == item.get("signal")
            ).order_by(core.SignalHistory.id.desc()))
            if exists is not None:
                continue
            payload = {
                "source":"AlgoTrade", "strategy":result.get("strategy"), "version":result.get("version"),
                "signal":item.get("signal"), "confidence_at_entry":item.get("confidence"),
                "score":result.get("score"), "checks":result.get("checks"), "reason":result.get("reason"),
                "execution_candidate":item, "timeframes":result.get("timeframes"),
                "history_snapshot": {"strategy":result.get("strategy"), "version":result.get("version"),
                    "timeframes":result.get("timeframes"), "checks":result.get("checks"),
                    "signal":item.get("signal"), "candle_time":candle, "immutable":True}
            }
            row=core.SignalHistory(user_id=user.id,symbol="XAU/USD",interval=tf,direction=item["signal"],
                headline=f"AlgoTrade {item['signal']} · {tf.upper()}",price=float(item["entry"]),payload=json.dumps(payload,ensure_ascii=False),
                outcome="OPEN",status="ACTIVE",source="AlgoTrade",candle_time=candle,created_at=datetime.now(timezone.utc))
            core._history_sync_row(row,payload)
            session.add(row)
        session.commit()
    return result
