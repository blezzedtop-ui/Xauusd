
"""
price_action_10_strategies.py

Implements 10 price-action strategies inspired by the uploaded
"15 NARX HARAKATI STRATEGIYASI.pdf".

Important:
- The PDF describes the setups visually and narratively (breakouts,
  retests, support/resistance, double tops/bottoms, triangles, etc.).
- It does NOT provide machine-readable numeric thresholds for every
  condition. Therefore the configurable values below (ATR buffers,
  tolerance, lookbacks, etc.) are explicit engineering parameters,
  not claims that those exact numbers appear in the PDF.

Input:
    pandas.DataFrame with columns:
    open, high, low, close
    index = datetime is recommended.

Output:
    DataFrame containing one row per candle and signals:
    BUY, SELL, or NO TRADE, plus entry, SL, TP, RR, strategy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass
class Config:
    atr_period: int = 14
    swing_lookback: int = 3
    sr_lookback: int = 30
    range_lookback: int = 20

    # Engineering parameters used to turn visual rules into explicit code.
    breakout_body_atr: float = 0.50
    retest_atr: float = 0.10
    sl_buffer_atr: float = 0.20
    same_level_tolerance_pct: float = 0.005  # 0.5%
    consolidation_atr: float = 1.50
    min_rr: float = 2.0
    preferred_rr: float = 3.0

    min_touches: int = 3
    max_bars_after_breakout: int = 8


def _validate(df: pd.DataFrame) -> pd.DataFrame:
    required = {"open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing OHLC columns: {sorted(missing)}")

    out = df.copy()
    for c in required:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=list(required))

    if out.empty:
        raise ValueError("No valid OHLC rows.")
    return out


def atr(df: pd.DataFrame, period: int) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def candle_body(df: pd.DataFrame) -> pd.Series:
    return (df["close"] - df["open"]).abs()


def bullish(df: pd.DataFrame) -> pd.Series:
    return df["close"] > df["open"]


def bearish(df: pd.DataFrame) -> pd.Series:
    return df["close"] < df["open"]


def pivot_highs(df: pd.DataFrame, left: int = 3, right: int = 3) -> List[int]:
    highs = df["high"].to_numpy()
    pivots = []
    for i in range(left, len(df) - right):
        window = highs[i-left:i+right+1]
        if highs[i] == np.max(window) and np.sum(window == highs[i]) == 1:
            pivots.append(i)
    return pivots


def pivot_lows(df: pd.DataFrame, left: int = 3, right: int = 3) -> List[int]:
    lows = df["low"].to_numpy()
    pivots = []
    for i in range(left, len(df) - right):
        window = lows[i-left:i+right+1]
        if lows[i] == np.min(window) and np.sum(window == lows[i]) == 1:
            pivots.append(i)
    return pivots


def _signal(
    side: str,
    entry: float,
    sl: float,
    rr: float,
    strategy: str,
    reason: str,
) -> Optional[Dict]:
    if not np.isfinite(entry) or not np.isfinite(sl):
        return None

    risk = abs(entry - sl)
    if risk <= 0:
        return None

    if side == "BUY":
        tp = entry + rr * risk
    else:
        tp = entry - rr * risk

    return {
        "signal": side,
        "entry": float(entry),
        "sl": float(sl),
        "tp": float(tp),
        "rr": float(rr),
        "strategy": strategy,
        "reason": reason,
    }


def _best_signal(candidates: List[Optional[Dict]], cfg: Config) -> Optional[Dict]:
    candidates = [x for x in candidates if x is not None]
    candidates = [x for x in candidates if x["rr"] >= cfg.min_rr]
    if not candidates:
        return None
    # Prefer the strategy with the largest configured RR.
    return max(candidates, key=lambda x: x["rr"])


def _line_value(p1: Tuple[int, float], p2: Tuple[int, float], x: int) -> float:
    i1, y1 = p1
    i2, y2 = p2
    if i2 == i1:
        return y1
    return y1 + (y2 - y1) * (x - i1) / (i2 - i1)


def strategy_1_sr_break_retest(df: pd.DataFrame, i: int, cfg: Config, a: float) -> Optional[Dict]:
    """Horizontal S/R breakout + retest."""
    if i < cfg.sr_lookback + 2 or not np.isfinite(a):
        return None

    w = df.iloc[i-cfg.sr_lookback:i]
    r = float(w["high"].max())
    s = float(w["low"].min())

    # BUY: previous candle breaks above R, current candle retests and closes above.
    if (
        df["close"].iloc[i-1] > r
        and df["open"].iloc[i-1] <= r
        and df["low"].iloc[i] <= r + cfg.retest_atr * a
        and df["close"].iloc[i] > r
    ):
        sl = float(df["low"].iloc[i] - cfg.sl_buffer_atr * a)
        return _signal("BUY", float(df["close"].iloc[i]), sl, cfg.preferred_rr,
                       "S1_SR_BREAK_RETEST", "Resistance breakout -> retest -> close above")

    if (
        df["close"].iloc[i-1] < s
        and df["open"].iloc[i-1] >= s
        and df["high"].iloc[i] >= s - cfg.retest_atr * a
        and df["close"].iloc[i] < s
    ):
        sl = float(df["high"].iloc[i] + cfg.sl_buffer_atr * a)
        return _signal("SELL", float(df["close"].iloc[i]), sl, cfg.preferred_rr,
                       "S1_SR_BREAK_RETEST", "Support breakdown -> retest -> close below")
    return None


def _double_bottom(df: pd.DataFrame, i: int, cfg: Config) -> Optional[Tuple[int, int, float, float]]:
    lows = pivot_lows(df.iloc[:i], cfg.swing_lookback, cfg.swing_lookback)
    if len(lows) < 2:
        return None
    p1, p2 = lows[-2], lows[-1]
    l1, l2 = float(df["low"].iloc[p1]), float(df["low"].iloc[p2])
    tol = cfg.same_level_tolerance_pct
    if abs(l1 - l2) / max(abs(l1), 1e-12) > tol:
        return None
    neckline = float(df["high"].iloc[p1:p2+1].max())
    return p1, p2, (l1 + l2) / 2.0, neckline


def strategy_2_double_bottom(df: pd.DataFrame, i: int, cfg: Config, a: float) -> Optional[Dict]:
    if i < 20 or not np.isfinite(a):
        return None
    db = _double_bottom(df, i, cfg)
    if not db:
        return None
    p1, p2, _, neckline = db

    # Breakout + retest confirmation.
    if (
        df["close"].iloc[i-1] > neckline
        and df["low"].iloc[i] <= neckline + cfg.retest_atr * a
        and df["close"].iloc[i] > neckline
    ):
        swing_low = min(float(df["low"].iloc[p1]), float(df["low"].iloc[p2]))
        sl = swing_low - cfg.sl_buffer_atr * a
        return _signal("BUY", float(df["close"].iloc[i]), sl, cfg.preferred_rr,
                       "S2_DOUBLE_BOTTOM", "Two lows near the same price -> neckline breakout -> retest")

    return None


def _double_top(df: pd.DataFrame, i: int, cfg: Config) -> Optional[Tuple[int, int, float, float]]:
    highs = pivot_highs(df.iloc[:i], cfg.swing_lookback, cfg.swing_lookback)
    if len(highs) < 2:
        return None
    p1, p2 = highs[-2], highs[-1]
    h1, h2 = float(df["high"].iloc[p1]), float(df["high"].iloc[p2])
    tol = cfg.same_level_tolerance_pct
    if abs(h1 - h2) / max(abs(h1), 1e-12) > tol:
        return None
    neckline = float(df["low"].iloc[p1:p2+1].min())
    return p1, p2, (h1 + h2) / 2.0, neckline


def strategy_6_double_top(df: pd.DataFrame, i: int, cfg: Config, a: float) -> Optional[Dict]:
    if i < 20 or not np.isfinite(a):
        return None
    dt = _double_top(df, i, cfg)
    if not dt:
        return None
    p1, p2, _, neckline = dt

    if (
        df["close"].iloc[i-1] < neckline
        and df["high"].iloc[i] >= neckline - cfg.retest_atr * a
        and df["close"].iloc[i] < neckline
    ):
        swing_high = max(float(df["high"].iloc[p1]), float(df["high"].iloc[p2]))
        sl = swing_high + cfg.sl_buffer_atr * a
        return _signal("SELL", float(df["close"].iloc[i]), sl, cfg.preferred_rr,
                       "S6_DOUBLE_TOP", "Two highs near the same price -> neckline breakdown -> retest")

    return None


def _triangle_lines(df: pd.DataFrame, i: int, cfg: Config):
    hs = pivot_highs(df.iloc[:i], cfg.swing_lookback, cfg.swing_lookback)
    ls = pivot_lows(df.iloc[:i], cfg.swing_lookback, cfg.swing_lookback)
    if len(hs) < 2 or len(ls) < 2:
        return None

    h1, h2 = hs[-2], hs[-1]
    l1, l2 = ls[-2], ls[-1]
    upper = ((h1, float(df["high"].iloc[h1])), (h2, float(df["high"].iloc[h2])))
    lower = ((l1, float(df["low"].iloc[l1])), (l2, float(df["low"].iloc[l2])))

    # Symmetrical triangle approximation:
    upper_slope = upper[1][1] - upper[0][1]
    lower_slope = lower[1][1] - lower[0][1]
    if not (upper_slope < 0 and lower_slope > 0):
        return None

    return upper, lower


def strategy_3_sym_triangle(df: pd.DataFrame, i: int, cfg: Config, a: float) -> Optional[Dict]:
    if i < 30 or not np.isfinite(a):
        return None
    lines = _triangle_lines(df, i, cfg)
    if not lines:
        return None
    upper, lower = lines
    up_now = _line_value(upper[0], upper[1], i)
    low_now = _line_value(lower[0], lower[1], i)
    up_prev = _line_value(upper[0], upper[1], i-1)
    low_prev = _line_value(lower[0], lower[1], i-1)

    if df["close"].iloc[i-1] > up_prev and df["low"].iloc[i] <= up_now + cfg.retest_atr*a and df["close"].iloc[i] > up_now:
        sl = float(df["low"].iloc[i] - cfg.sl_buffer_atr*a)
        return _signal("BUY", float(df["close"].iloc[i]), sl, cfg.preferred_rr,
                       "S3_SYMMETRICAL_TRIANGLE", "Upper triangle line breakout -> retest -> confirmation")

    if df["close"].iloc[i-1] < low_prev and df["high"].iloc[i] >= low_now - cfg.retest_atr*a and df["close"].iloc[i] < low_now:
        sl = float(df["high"].iloc[i] + cfg.sl_buffer_atr*a)
        return _signal("SELL", float(df["close"].iloc[i]), sl, cfg.preferred_rr,
                       "S3_SYMMETRICAL_TRIANGLE", "Lower triangle line breakdown -> retest -> confirmation")

    return None


def strategy_4_day_levels(df: pd.DataFrame, i: int, cfg: Config, a: float) -> Optional[Dict]:
    """
    Uses the prior completed daily candle as the reference:
    previous day high/low/open. Current timeframe must have a DatetimeIndex.
    """
    if not isinstance(df.index, pd.DatetimeIndex) or i < 5 or not np.isfinite(a):
        return None

    t = df.index[i]
    day = t.normalize()
    prev_rows = df.loc[df.index.normalize() < day]
    if prev_rows.empty:
        return None
    prev_day = prev_rows.index.normalize().max()
    d = df.loc[df.index.normalize() == prev_day]
    if d.empty:
        return None

    r1 = float(d["high"].max())
    s1 = float(d["low"].min())

    # Day-2 breakout/retest.
    if (
        df["close"].iloc[i-1] > r1
        and df["low"].iloc[i] <= r1 + cfg.retest_atr*a
        and df["close"].iloc[i] > r1
    ):
        sl = float(df["low"].iloc[i] - cfg.sl_buffer_atr*a)
        return _signal("BUY", float(df["close"].iloc[i]), sl, cfg.preferred_rr,
                       "S4_DAILY_LEVELS", "Previous-day resistance breakout + retest")

    if (
        df["close"].iloc[i-1] < s1
        and df["high"].iloc[i] >= s1 - cfg.retest_atr*a
        and df["close"].iloc[i] < s1
    ):
        sl = float(df["high"].iloc[i] + cfg.sl_buffer_atr*a)
        return _signal("SELL", float(df["close"].iloc[i]), sl, cfg.preferred_rr,
                       "S4_DAILY_LEVELS", "Previous-day support breakdown + retest")

    return None


def strategy_5_three_levels(df: pd.DataFrame, i: int, cfg: Config, a: float) -> Optional[Dict]:
    """
    Three horizontal levels based on rolling range quartiles/structure.
    This is an engineering approximation because the PDF labels three
    levels visually but does not define a numeric construction formula.
    """
    if i < cfg.sr_lookback or not np.isfinite(a):
        return None
    w = df.iloc[i-cfg.sr_lookback:i]
    lo, hi = float(w["low"].min()), float(w["high"].max())
    width = hi - lo
    if width <= 0:
        return None

    z1 = lo + width / 3.0
    z2 = lo + 2.0 * width / 3.0
    z3 = hi

    # Rejection from upper level -> SELL.
    if df["high"].iloc[i] >= z3 - cfg.retest_atr*a and df["close"].iloc[i] < z3:
        sl = float(df["high"].iloc[i] + cfg.sl_buffer_atr*a)
        return _signal("SELL", float(df["close"].iloc[i]), sl, cfg.preferred_rr,
                       "S5_THREE_LEVELS", "Upper level rejection; target next lower level(s)")

    # Rejection from lower level -> BUY.
    if df["low"].iloc[i] <= z1 + cfg.retest_atr*a and df["close"].iloc[i] > z1:
        sl = float(df["low"].iloc[i] - cfg.sl_buffer_atr*a)
        return _signal("BUY", float(df["close"].iloc[i]), sl, cfg.preferred_rr,
                       "S5_THREE_LEVELS", "Lower level rejection; target next higher level(s)")

    return None


def strategy_7_trendline_break_retest(df: pd.DataFrame, i: int, cfg: Config, a: float) -> Optional[Dict]:
    if i < 30 or not np.isfinite(a):
        return None

    hs = pivot_highs(df.iloc[:i], cfg.swing_lookback, cfg.swing_lookback)
    ls = pivot_lows(df.iloc[:i], cfg.swing_lookback, cfg.swing_lookback)
    body = float(candle_body(df).iloc[i-1])

    if len(hs) >= 3:
        p = hs[-3:]
        vals = [float(df["high"].iloc[x]) for x in p]
        if vals[0] > vals[1] > vals[2]:
            tl_prev = _line_value((p[0], vals[0]), (p[-1], vals[-1]), i-1)
            tl_now = _line_value((p[0], vals[0]), (p[-1], vals[-1]), i)
            if df["close"].iloc[i-1] > tl_prev and body >= cfg.breakout_body_atr*a and \
               df["low"].iloc[i] <= tl_now + cfg.retest_atr*a and df["close"].iloc[i] > tl_now:
                sl = float(df["low"].iloc[i] - cfg.sl_buffer_atr*a)
                return _signal("BUY", float(df["close"].iloc[i]), sl, cfg.preferred_rr,
                               "S7_TRENDLINE_BREAK_RETEST", "Downtrend resistance broken + retest")

    if len(ls) >= 3:
        p = ls[-3:]
        vals = [float(df["low"].iloc[x]) for x in p]
        if vals[0] < vals[1] < vals[2]:
            tl_prev = _line_value((p[0], vals[0]), (p[-1], vals[-1]), i-1)
            tl_now = _line_value((p[0], vals[0]), (p[-1], vals[-1]), i)
            if df["close"].iloc[i-1] < tl_prev and body >= cfg.breakout_body_atr*a and \
               df["high"].iloc[i] >= tl_now - cfg.retest_atr*a and df["close"].iloc[i] < tl_now:
                sl = float(df["high"].iloc[i] + cfg.sl_buffer_atr*a)
                return _signal("SELL", float(df["close"].iloc[i]), sl, cfg.preferred_rr,
                               "S7_TRENDLINE_BREAK_RETEST", "Uptrend support broken + retest")

    return None


def strategy_8_resistance_zone(df: pd.DataFrame, i: int, cfg: Config, a: float) -> Optional[Dict]:
    if i < cfg.sr_lookback + 2 or not np.isfinite(a):
        return None
    w = df.iloc[i-cfg.sr_lookback:i]
    r_high = float(w["high"].max())
    r_low = float(w["high"].quantile(0.85))

    # Zone is [r_low, r_high].
    if (
        df["close"].iloc[i-1] > r_high
        and df["low"].iloc[i] <= r_high + cfg.retest_atr*a
        and df["close"].iloc[i] > r_high
    ):
        sl = float(r_low - cfg.sl_buffer_atr*a)
        return _signal("BUY", float(df["close"].iloc[i]), sl, cfg.preferred_rr,
                       "S8_RESISTANCE_ZONE", "Resistance zone breakout + retest")

    # Failure/rejection from zone -> SELL.
    if df["high"].iloc[i] >= r_high and df["close"].iloc[i] < r_high:
        sl = float(df["high"].iloc[i] + cfg.sl_buffer_atr*a)
        return _signal("SELL", float(df["close"].iloc[i]), sl, cfg.preferred_rr,
                       "S8_RESISTANCE_ZONE", "Resistance zone rejection")

    return None


def strategy_9_range_double_bottom(df: pd.DataFrame, i: int, cfg: Config, a: float) -> Optional[Dict]:
    if i < cfg.range_lookback + 5 or not np.isfinite(a):
        return None

    w = df.iloc[i-cfg.range_lookback:i]
    r = float(w["high"].max())
    s = float(w["low"].min())
    width = r - s
    if width <= 0:
        return None

    # Price is close to support.
    near_support = (float(df["close"].iloc[i]) - s) <= 0.15 * width
    if not near_support:
        return None

    db = _double_bottom(df, i, cfg)
    if not db:
        return None

    p1, p2, _, neckline = db
    if df["close"].iloc[i-1] > neckline and df["close"].iloc[i] > neckline:
        swing_low = min(float(df["low"].iloc[p1]), float(df["low"].iloc[p2]))
        sl = swing_low - cfg.sl_buffer_atr*a
        # RR is forced to at least min_rr by using the preferred RR.
        return _signal("BUY", float(df["close"].iloc[i]), sl, cfg.preferred_rr,
                       "S9_RANGE_DOUBLE_BOTTOM", "Range support + double bottom + neckline confirmation")
    return None


def strategy_10_consolidation_sr(df: pd.DataFrame, i: int, cfg: Config, a: float) -> Optional[Dict]:
    if i < cfg.range_lookback + 1 or not np.isfinite(a):
        return None

    w = df.iloc[i-cfg.range_lookback:i]
    r = float(w["high"].max())
    s = float(w["low"].min())
    box = r - s

    # Consolidation definition: range smaller than configured ATR multiple.
    if box > cfg.consolidation_atr * a:
        return None

    # SELL after rejection from resistance.
    if df["high"].iloc[i] >= r and df["close"].iloc[i] < r:
        sl = float(df["high"].iloc[i] + cfg.sl_buffer_atr*a)
        return _signal("SELL", float(df["close"].iloc[i]), sl, cfg.preferred_rr,
                       "S10_CONSOLIDATION_SR", "Consolidation range + resistance rejection")

    # BUY after support rejection.
    if df["low"].iloc[i] <= s and df["close"].iloc[i] > s:
        sl = float(df["low"].iloc[i] - cfg.sl_buffer_atr*a)
        return _signal("BUY", float(df["close"].iloc[i]), sl, cfg.preferred_rr,
                       "S10_CONSOLIDATION_SR", "Consolidation range + support rejection")

    return None


STRATEGIES = [
    strategy_1_sr_break_retest,
    strategy_2_double_bottom,
    strategy_3_sym_triangle,
    strategy_4_day_levels,
    strategy_5_three_levels,
    strategy_6_double_top,
    strategy_7_trendline_break_retest,
    strategy_8_resistance_zone,
    strategy_9_range_double_bottom,
    strategy_10_consolidation_sr,
]


def analyze(df: pd.DataFrame, cfg: Optional[Config] = None) -> pd.DataFrame:
    """
    Run all 10 strategies candle-by-candle.

    A candle may trigger multiple strategies. The returned result keeps:
      primary_signal = strongest available signal (highest RR; ties by strategy order)
      all_signals = list of all detected setups
    """
    cfg = cfg or Config()
    df = _validate(df)
    a = atr(df, cfg.atr_period)

    rows = []
    for i in range(len(df)):
        candidates = []
        if np.isfinite(a.iloc[i]):
            for fn in STRATEGIES:
                try:
                    candidates.append(fn(df, i, cfg, float(a.iloc[i])))
                except Exception:
                    # One strategy failing should not break the full analyzer.
                    candidates.append(None)

        valid = [x for x in candidates if x is not None and x["rr"] >= cfg.min_rr]
        primary = valid[0] if valid else None

        row = {
            "signal": primary["signal"] if primary else "NO TRADE",
            "entry": primary["entry"] if primary else np.nan,
            "sl": primary["sl"] if primary else np.nan,
            "tp": primary["tp"] if primary else np.nan,
            "rr": primary["rr"] if primary else np.nan,
            "strategy": primary["strategy"] if primary else "",
            "reason": primary["reason"] if primary else "",
            "atr": float(a.iloc[i]) if np.isfinite(a.iloc[i]) else np.nan,
            "all_signals": valid,
        }
        rows.append(row)

    return pd.DataFrame(rows, index=df.index)


def latest_signal(df: pd.DataFrame, cfg: Optional[Config] = None) -> Dict:
    """Return only the latest candle's analysis."""
    out = analyze(df, cfg)
    r = out.iloc[-1]
    return {
        "signal": r["signal"],
        "entry": None if pd.isna(r["entry"]) else float(r["entry"]),
        "sl": None if pd.isna(r["sl"]) else float(r["sl"]),
        "tp": None if pd.isna(r["tp"]) else float(r["tp"]),
        "rr": None if pd.isna(r["rr"]) else float(r["rr"]),
        "strategy": r["strategy"],
        "reason": r["reason"],
        "atr": None if pd.isna(r["atr"]) else float(r["atr"]),
        "all_signals": r["all_signals"],
    }


if __name__ == "__main__":
    # Example:
    # df = pd.read_csv("XAUUSD_M30.csv", parse_dates=["time"], index_col="time")
    # result = analyze(df)
    # print(latest_signal(df))
    print("Module loaded. Use analyze(df) or latest_signal(df).")
