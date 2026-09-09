from __future__ import annotations

from typing import Any
import json
import math


def _f(c: dict[str, Any], k: str = "close") -> float:
    """Read a candle field; default to close for backward-compatible callers."""
    return float(c[k])


def _swings(candles: list[dict[str, Any]], window: int = 2):
    highs, lows = [], []
    n = len(candles)
    for i in range(window, n - window):
        h = _f(candles[i], "high")
        l = _f(candles[i], "low")
        if h >= max(_f(candles[j], "high") for j in range(i-window, i+window+1)):
            highs.append((i, h))
        if l <= min(_f(candles[j], "low") for j in range(i-window, i+window+1)):
            lows.append((i, l))
    return highs, lows


def _pct(a: float, b: float) -> float:
    return abs(a - b) / max(abs(b), 1e-9)


def _atr(candles: list[dict[str, Any]], n: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    trs = []
    for i in range(max(1, len(candles)-n), len(candles)):
        c, p = candles[i], candles[i-1]
        trs.append(max(_f(c,"high")-_f(c,"low"), abs(_f(c,"high")-_f(p,"close")), abs(_f(c,"low")-_f(p,"close"))))
    return sum(trs) / max(len(trs), 1)


def _result(name: str, signal: str, reason: str, points: list[int] | None = None) -> dict[str, Any]:
    return {"name": name, "signal": signal, "reason": reason, "points": points or []}


def detect_book_patterns(candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(candles) < 40:
        return [_result("Book pattern scan", "WAIT", "Not enough candles for the book-pattern scan.")]
    highs, lows = _swings(candles, 2)
    close = _f(candles[-1], "close")
    atr = max(_atr(candles), close * 0.0002)
    out: list[dict[str, Any]] = []

    # Double Top / Bottom: two similar swing extremes with a neckline between them,
    # confirmed by a close through that neckline.
    if len(highs) >= 2:
        a, b = highs[-2], highs[-1]
        if b[0] > a[0] and _pct(a[1], b[1]) <= 0.02:
            neck = min(_f(candles[i], "low") for i in range(a[0], b[0]+1))
            sig = "SELL" if close < neck else "WAIT"
            out.append(_result("Double Top", sig, f"Two similar highs; neckline {neck:.4f}." + (" Close confirmed below neckline." if sig=="SELL" else " Waiting for neckline break."), [a[0], b[0]]))
    if len(lows) >= 2:
        a, b = lows[-2], lows[-1]
        if b[0] > a[0] and _pct(a[1], b[1]) <= 0.02:
            neck = max(_f(candles[i], "high") for i in range(a[0], b[0]+1))
            sig = "BUY" if close > neck else "WAIT"
            out.append(_result("Double Bottom", sig, f"Two similar lows; neckline {neck:.4f}." + (" Close confirmed above neckline." if sig=="BUY" else " Waiting for neckline break."), [a[0], b[0]]))

    # Head & Shoulders / inverse: last five meaningful swings form shoulder-head-shoulder geometry.
    if len(highs) >= 3:
        h1, h2, h3 = highs[-3:]
        if h2[1] > h1[1] and h2[1] > h3[1] and _pct(h1[1], h3[1]) <= 0.03:
            neck = min(_f(candles[i], "low") for i in range(h1[0], h3[0]+1))
            sig = "SELL" if close < neck else "WAIT"
            out.append(_result("Head & Shoulders", sig, f"Center high exceeds both shoulders; neckline {neck:.4f}." + (" Break confirmed." if sig=="SELL" else " Waiting for neckline break."), [h1[0], h2[0], h3[0]]))
    if len(lows) >= 3:
        l1, l2, l3 = lows[-3:]
        if l2[1] < l1[1] and l2[1] < l3[1] and _pct(l1[1], l3[1]) <= 0.03:
            neck = max(_f(candles[i], "high") for i in range(l1[0], l3[0]+1))
            sig = "BUY" if close > neck else "WAIT"
            out.append(_result("Inverse Head & Shoulders", sig, f"Center low is below both shoulders; neckline {neck:.4f}." + (" Break confirmed." if sig=="BUY" else " Waiting for neckline break."), [l1[0], l2[0], l3[0]]))

    # Triangles: use recent swing slopes and a flat boundary approximation.
    if len(highs) >= 3 and len(lows) >= 3:
        hs, ls = highs[-3:], lows[-3:]
        hr = [x[1] for x in hs]; lr = [x[1] for x in ls]
        hflat = _pct(max(hr), min(hr)) <= 0.02
        lflat = _pct(max(lr), min(lr)) <= 0.02
        rising_lows = lr[0] < lr[-1] and (lr[-1]-lr[0]) > atr*0.5
        falling_highs = hr[0] > hr[-1] and (hr[0]-hr[-1]) > atr*0.5
        resistance = max(hr); support = min(lr)
        if hflat and rising_lows:
            sig = "BUY" if close > resistance else "WAIT"
            out.append(_result("Ascending Triangle", sig, f"Flat resistance near {resistance:.4f} with rising lows." + (" Break confirmed." if sig=="BUY" else " Waiting for resistance break."), [x[0] for x in hs+ls]))
        if lflat and falling_highs:
            sig = "SELL" if close < support else "WAIT"
            out.append(_result("Descending Triangle", sig, f"Flat support near {support:.4f} with falling highs." + (" Break confirmed." if sig=="SELL" else " Waiting for support break."), [x[0] for x in hs+ls]))
        if falling_highs and rising_lows:
            upper, lower = max(hr), min(lr)
            sig = "BUY" if close > upper else "SELL" if close < lower else "WAIT"
            out.append(_result("Symmetrical Triangle", sig, f"Converging lower highs and higher lows; boundaries {lower:.4f}–{upper:.4f}."))

    # Flags: short counter-move after a directional impulse.
    if len(candles) >= 24:
        pole = candles[-24:-12]; flag = candles[-12:]
        pole_move = _f(pole[-1],"close") - _f(pole[0],"open")
        flag_move = _f(flag[-1],"close") - _f(flag[0],"open")
        if pole_move > atr*4 and flag_move < 0 and abs(flag_move) < pole_move*0.6:
            boundary = max(_f(c,"high") for c in flag)
            sig = "BUY" if close > boundary else "WAIT"
            out.append(_result("Bullish Flag", sig, f"Bullish impulse followed by a smaller counter-move; breakout {boundary:.4f}."))
        if pole_move < -atr*4 and flag_move > 0 and abs(flag_move) < abs(pole_move)*0.6:
            boundary = min(_f(c,"low") for c in flag)
            sig = "SELL" if close < boundary else "WAIT"
            out.append(_result("Bearish Flag", sig, f"Bearish impulse followed by a smaller counter-move; breakout {boundary:.4f}."))

    # Wedge: converging swing boundaries. Falling wedge -> bullish breakout; rising wedge -> bearish breakout.
    if len(highs) >= 3 and len(lows) >= 3:
        hr = [x[1] for x in highs[-3:]]; lr = [x[1] for x in lows[-3:]]
        high_drop = hr[0] - hr[-1]; low_drop = lr[0] - lr[-1]
        high_rise = hr[-1] - hr[0]; low_rise = lr[-1] - lr[0]
        if high_drop > atr and low_drop > atr and high_drop < low_drop:
            upper = hr[-1]; sig = "BUY" if close > upper else "WAIT"
            out.append(_result("Falling Wedge", sig, f"Both boundaries fall and converge; upper boundary {upper:.4f}."))
        if high_rise > atr and low_rise > atr and high_rise > low_rise:
            lower = lr[-1]; sig = "SELL" if close < lower else "WAIT"
            out.append(_result("Rising Wedge", sig, f"Both boundaries rise and converge; lower boundary {lower:.4f}."))

    if not out:
        out.append(_result("Book pattern scan", "WAIT", "No confirmed book pattern on the current chart."))
    return out


def book_signal(candles: list[dict[str, Any]]) -> dict[str, Any]:
    patterns = detect_book_patterns(candles)
    buys = [p for p in patterns if p["signal"] == "BUY"]
    sells = [p for p in patterns if p["signal"] == "SELL"]
    if buys and not sells:
        signal = "BUY"
    elif sells and not buys:
        signal = "SELL"
    else:
        signal = "WAIT"
    atr = max(_atr(candles), _f(candles[-1],"close") * 0.0002) if candles else 0.0
    price = _f(candles[-1], "close") if candles else 0.0
    if signal == "BUY":
        entry = price; sl = price - 1.2*atr; tp = [price + 2.0*atr, price + 3.0*atr]
    elif signal == "SELL":
        entry = price; sl = price + 1.2*atr; tp = [price - 2.0*atr, price - 3.0*atr]
    else:
        entry = sl = None; tp = []
    return {"signal": signal, "entry": entry, "stop_loss": sl, "take_profit": tp,
            "patterns": patterns, "confirmed_patterns": buys+sells,
            "reason": "; ".join(p["reason"] for p in patterns if p["signal"] != "WAIT") or patterns[0]["reason"]}


def c(candles, k):
    return candles[k]
