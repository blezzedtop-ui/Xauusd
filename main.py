
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv
from openai import OpenAI
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from price_action_10_strategies import Config, analyze, latest_signal

load_dotenv()

API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()
SYMBOL = os.getenv("SYMBOL", "XAU/USD").strip()
INTERVAL = os.getenv("INTERVAL", "30min").strip()
OUTPUTSIZE = int(os.getenv("OUTPUTSIZE", "300"))
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "15"))
AI_CACHE_SECONDS = int(os.getenv("AI_CACHE_SECONDS", "45"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4").strip()


BASE = "https://api.twelvedata.com"

app = FastAPI(title="XAUUSD Price Action AI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def fetch_candles() -> pd.DataFrame:
    if not API_KEY or API_KEY == "YOUR_API_KEY_HERE":
        raise RuntimeError("TWELVE_DATA_API_KEY is not configured.")

    params = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "outputsize": OUTPUTSIZE,
        "apikey": API_KEY,
        "timezone": "UTC",
        "order": "ASC",
    }
    r = requests.get(f"{BASE}/time_series", params=params, timeout=20)
    r.raise_for_status()
    payload = r.json()

    if payload.get("status") == "error":
        raise RuntimeError(payload.get("message", "Market-data API error."))

    values = payload.get("values", [])
    if not values:
        raise RuntimeError("No candle data returned.")

    df = pd.DataFrame(values)
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["datetime", "open", "high", "low", "close"])
    df = df.sort_values("datetime").set_index("datetime")
    return df


def json_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for ts, row in df.iterrows():
        rows.append(
            {
                "time": int(ts.timestamp()),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            }
        )
    return rows


_ai_cache = {"at": 0.0, "data": None}


def _build_ai_snapshot(df: pd.DataFrame, analysis_df: pd.DataFrame) -> dict:
    tail = df.tail(40).copy()
    rows = []
    for ts, r in tail.iterrows():
        rows.append({
            "time": str(ts),
            "open": round(float(r["open"]), 3),
            "high": round(float(r["high"]), 3),
            "low": round(float(r["low"]), 3),
            "close": round(float(r["close"]), 3),
        })

    a = analysis_df.iloc[-1]
    return {
        "symbol": SYMBOL,
        "timeframe": INTERVAL,
        "last_price": round(float(df["close"].iloc[-1]), 3),
        "atr14": None if pd.isna(a["atr"]) else round(float(a["atr"]), 4),
        "rule_engine_signal": a["signal"],
        "rule_engine_strategy": a["strategy"],
        "rule_engine_entry": None if pd.isna(a["entry"]) else round(float(a["entry"]), 3),
        "rule_engine_sl": None if pd.isna(a["sl"]) else round(float(a["sl"]), 3),
        "rule_engine_tp": None if pd.isna(a["tp"]) else round(float(a["tp"]), 3),
        "rule_engine_rr": None if pd.isna(a["rr"]) else round(float(a["rr"]), 2),
        "candles": rows,
    }


def _generate_openai_analysis_uncached(snapshot: dict) -> dict:
    if not OPENAI_API_KEY:
        return {
            "available": False,
            "error": "OPENAI_API_KEY is not configured.",
        }

    client = OpenAI(api_key=OPENAI_API_KEY)

    system = """You are a disciplined XAUUSD M30 technical-analysis assistant.
Use ONLY the supplied OHLC snapshot and rule-engine result. Do not invent prices,
candles, indicators, news, order flow, or fundamentals that are not supplied.
The 10 strategy rule engine is the primary signal source. Your role is to:
1) validate/criticize the rule-engine setup using the supplied candles,
2) describe trend/market structure visible in those candles,
3) identify support/resistance zones that can be inferred from the supplied OHLC,
4) provide a confidence score from 0 to 100,
5) produce a final recommendation of BUY, SELL, or NO TRADE.
When the evidence is insufficient or conflicting, choose NO TRADE.
Do not claim certainty or guaranteed profit.

Return strict JSON with these keys:
final_signal, confidence, market_bias, structure, support_zones, resistance_zones,
entry, stop_loss, take_profit, rr, strategy_alignment, reasons, risks.

support_zones and resistance_zones are arrays of objects:
{"low": number, "high": number, "reason": string}
reasons and risks are arrays of short strings.
Numbers must be numeric or null.
"""

    user = f"""Analyze this live XAUUSD M30 snapshot:

{snapshot}

Important:
- The supplied rule_engine_* fields come from the deterministic 10-strategy engine.
- Do not override a valid rule-engine signal without explaining the conflict.
- Prefer NO TRADE when there is no clean confirmation.
"""

    try:
        resp = client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        text = resp.output_text.strip()
        import json
        data = json.loads(text)
        data["available"] = True
        return data
    except Exception as e:
        return {
            "available": False,
            "error": str(e),
        }


def generate_openai_analysis(snapshot: dict) -> dict:
    import time
    now = time.time()
    cached = _ai_cache.get("data")
    if cached is not None and now - float(_ai_cache.get("at", 0.0)) < AI_CACHE_SECONDS:
        return cached
    data = _generate_openai_analysis_uncached(snapshot)
    if data.get("available"):
        _ai_cache["at"] = now
        _ai_cache["data"] = data
    return data



@app.get("/api/health")
def health():
    return {
        "ok": True,
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "provider": "Twelve Data",
        "server_time": datetime.now(timezone.utc).isoformat(),
        "poll_seconds": POLL_SECONDS,
        "market_key_configured": bool(API_KEY and API_KEY != "YOUR_API_KEY_HERE"),
        "openai_key_configured": bool(OPENAI_API_KEY and OPENAI_API_KEY != "YOUR_OPENAI_API_KEY_HERE"),
    }


@app.get("/api/market")
def market():
    try:
        df = fetch_candles()
        cfg = Config()
        analysis_df = analyze(df, cfg)
        latest = latest_signal(df, cfg)

        latest_row = analysis_df.iloc[-1]
        signal_age = str(df.index[-1])

        return {
            "symbol": SYMBOL,
            "interval": INTERVAL,
            "provider": "Twelve Data",
            "last_candle_time": signal_age,
            "candles": json_records(df),
            "signal": latest,
            "history": [
                {
                    "time": int(ts.timestamp()),
                    "signal": row["signal"],
                    "entry": None if pd.isna(row["entry"]) else float(row["entry"]),
                    "sl": None if pd.isna(row["sl"]) else float(row["sl"]),
                    "tp": None if pd.isna(row["tp"]) else float(row["tp"]),
                    "rr": None if pd.isna(row["rr"]) else float(row["rr"]),
                    "strategy": row["strategy"],
                }
                for ts, row in analysis_df.tail(30).iterrows()
                if row["signal"] != "NO TRADE"
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/ai-analysis")
def ai_analysis():
    try:
        df = fetch_candles()
        cfg = Config()
        analysis_df = analyze(df, cfg)
        snapshot = _build_ai_snapshot(df, analysis_df)
        ai = generate_openai_analysis(snapshot)
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "provider": "OpenAI",
            "model": OPENAI_MODEL,
            "ai": ai,
            "rule_engine": snapshot,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")

# --- Advanced analysis add-on: does not replace the existing /api/market flow. ---
from advanced_analysis import analyze_advanced

REALMARKET_API_KEY_ADV = os.getenv("REALMARKET_API_KEY", "").strip()
REALMARKET_BASE_ADV = "https://api.realmarketapi.com"

def _advanced_rm_get(path: str, params: dict):
    if not REALMARKET_API_KEY_ADV:
        return None
    q = {"apiKey": REALMARKET_API_KEY_ADV, **params}
    r = requests.get(REALMARKET_BASE_ADV + path, params=q, timeout=20)
    r.raise_for_status()
    return r.json()

def _advanced_unwrap(payload):
    if isinstance(payload, list): return payload
    for k in ("data","Data","items","Items","candles","Candles","results","Results","values"):
        if isinstance(payload, dict) and isinstance(payload.get(k), list): return payload[k]
    return []

def _advanced_norm(c):
    t=c.get("openTime",c.get("OpenTime",c.get("time",c.get("timestamp",c.get("Timestamp")))))
    o=c.get("openPrice",c.get("OpenPrice",c.get("open",c.get("Open"))))
    h=c.get("highPrice",c.get("HighPrice",c.get("high",c.get("High"))))
    l=c.get("lowPrice",c.get("LowPrice",c.get("low",c.get("Low"))))
    cl=c.get("closePrice",c.get("ClosePrice",c.get("close",c.get("Close"))))
    if isinstance(t,(int,float)): ts=t/1000 if t>1e12 else t
    else: ts=pd.Timestamp(t).timestamp()
    return {"time":int(ts),"open":float(o),"high":float(h),"low":float(l),"close":float(cl)}

def _advanced_candles(timeframe: str):
    if REALMARKET_API_KEY_ADV:
        payload=_advanced_rm_get("/api/v1/candle",{"symbolCode":"XAUUSD","timeFrame":timeframe})
        arr=[_advanced_norm(x) for x in _advanced_unwrap(payload)]
        return sorted({x["time"]:x for x in arr}.values(), key=lambda x:x["time"])[-300:]
    # Preserve the original working site's Twelve Data source when RealMarketAPI is not configured.
    return [
        {"time":int(ts.timestamp()),"open":float(r["open"]),"high":float(r["high"]),"low":float(r["low"]),"close":float(r["close"])}
        for ts,r in fetch_candles().iterrows()
    ][-300:]

@app.get("/api/advanced-analysis")
def advanced_analysis(timeframe: str = "M30"):
    try:
        cs=_advanced_candles(timeframe)
        if len(cs)<40: raise RuntimeError("Not enough candles for advanced analysis.")
        return analyze_advanced(cs,"XAUUSD",timeframe)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
