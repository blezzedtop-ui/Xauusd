
from __future__ import annotations
import os, time, json
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd
import numpy as np
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
import websockets

from price_action_10_strategies import Config, analyze as secondary_analyze, latest_signal as secondary_latest

load_dotenv()
REALMARKET_API_KEY = os.getenv("REALMARKET_API_KEY","").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY","").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL","gpt-5.6-luna").strip()
BASE="https://api.realmarketapi.com"
WS_BASE="wss://api.realmarketapi.com/price"

app=FastAPI(title="XAUUSD AI Multi-Engine Analyzer")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
openai = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
_ai_cache={"at":0.0,"data":None}

TF_MAP={"M1":"M1","M5":"M5","M15":"M15","M30":"M30","H1":"H1","H4":"H4","D1":"D1"}

def api_get(path:str, params:dict):
    if not REALMARKET_API_KEY: raise RuntimeError("REALMARKET_API_KEY is not configured on Railway.")
    q={"apiKey":REALMARKET_API_KEY, **params}
    r=requests.get(BASE+path,params=q,timeout=20)
    text=r.text
    try: payload=r.json()
    except: payload={"raw":text}
    if not r.ok: raise RuntimeError(f"RealMarketAPI {r.status_code}: {payload}")
    return payload

def unwrap(payload):
    if isinstance(payload,list): return payload
    for k in ["data","Data","items","Items","candles","Candles","results","Results","values"]:
        if isinstance(payload.get(k),list): return payload[k]
    return []

def norm(c):
    t=c.get("openTime",c.get("OpenTime",c.get("time",c.get("timestamp",c.get("Timestamp")))))
    o=c.get("openPrice",c.get("OpenPrice",c.get("open",c.get("Open"))))
    h=c.get("highPrice",c.get("HighPrice",c.get("high",c.get("High"))))
    l=c.get("lowPrice",c.get("LowPrice",c.get("low",c.get("Low"))))
    cl=c.get("closePrice",c.get("ClosePrice",c.get("close",c.get("Close"))))
    v=c.get("volume",c.get("Volume",0))
    if isinstance(t,(int,float)): ts=t/1000 if t>1e12 else t
    else: ts=pd.Timestamp(t).timestamp()
    return {"time":int(ts),"open":float(o),"high":float(h),"low":float(l),"close":float(cl),"volume":float(v or 0)}

def get_candles(symbol="XAUUSD",tf="M5"):
    payload=api_get("/api/v1/candle",{"symbolCode":symbol,"timeFrame":tf})
    arr=[norm(x) for x in unwrap(payload)]
    arr=[x for x in arr if all(np.isfinite(x[k]) for k in ["time","open","high","low","close"])]
    if len(arr)<60:
        hours={"M1":6,"M5":24,"M15":72,"M30":144,"H1":300,"H4":720,"D1":3650}.get(tf,72)
        end=datetime.now(timezone.utc); start=end-pd.Timedelta(hours=hours)
        try:
            hp=api_get("/api/v1/history",{"symbolCode":symbol,"timeFrame":tf,"startTime":start.isoformat(),"endTime":end.isoformat(),"pageNumber":"1","pageSize":"300"})
            h=[norm(x) for x in unwrap(hp)]
            if h: arr=h
        except Exception: pass
    ded={x["time"]:x for x in arr}
    return sorted(ded.values(),key=lambda x:x["time"])[-300:]

def candles_df(cs):
    return pd.DataFrame(cs,index=pd.to_datetime([x["time"] for x in cs],unit="s",utc=True))[["open","high","low","close"]]

def pct(a,b):
    return abs(a-b)/max((a+b)/2,1e-12)

def local_extrema(cs,look=2):
    highs=[]; lows=[]
    for i in range(look,len(cs)-look):
        hi=all(cs[i]["high"]>=cs[i-j]["high"] and cs[i]["high"]>=cs[i+j]["high"] for j in range(1,look+1))
        lo=all(cs[i]["low"]<=cs[i-j]["low"] and cs[i]["low"]<=cs[i+j]["low"] for j in range(1,look+1))
        if hi: highs.append((i,cs[i]["high"]))
        if lo: lows.append((i,cs[i]["low"]))
    return highs,lows

def atr(cs,p=14):
    if len(cs)<=p: return 0.0
    tr=[]
    for i in range(1,len(cs)):
        tr.append(max(cs[i]["high"]-cs[i]["low"],abs(cs[i]["high"]-cs[i-1]["close"]),abs(cs[i]["low"]-cs[i-1]["close"])))
    return float(np.mean(tr[-p:]))

def trend(cs):
    if len(cs)<20: return "NEUTRAL"
    a=np.mean([x["close"] for x in cs[-20:]]); b=np.mean([x["close"] for x in cs[-8:]])
    if b>a*1.001: return "BULLISH"
    if b<a*0.999: return "BEARISH"
    return "NEUTRAL"

def pivots(c):
    p=(c["high"]+c["low"]+c["close"])/3
    return {"pivot":p,"r1":2*p-c["low"],"r2":p+(c["high"]-c["low"]),"r3":c["high"]+2*(p-c["low"]),
            "s1":2*p-c["high"],"s2":p-(c["high"]-c["low"]),"s3":c["low"]-2*(c["high"]-p)}

# ---- SIMPLE TRADING Book v1 engine ----
def book_patterns(cs):
    out=[]; highs,lows=local_extrema(cs,2); price=cs[-1]["close"]
    h=highs[-6:]; l=lows[-6:]
    def add(name,direction,entry,sl,tp,confidence,why):
        if all(np.isfinite(v) for v in [entry,sl,tp]) and abs(entry-sl)>0:
            out.append({"name":name,"direction":direction,"entry":entry,"sl":sl,"tp":tp,"confidence":confidence,"why":why})
    if len(h)>=2:
        a,b=h[-2],h[-1]
        mids=[x for x in l if a[0]<x[0]<b[0]]
        if mids and pct(a[1],b[1])<=.02:
            n=mids[-1][1]
            if price<n:
                height=max(a[1],b[1])-n
                add("Double Top","SELL",price,max(a[1],b[1]),n-height,88,f"Two highs within 2%; neckline {n:.2f} broken.")
        if len(h)>=3:
            A,B,C=h[-3],h[-2],h[-1]
            if B[1]>A[1] and B[1]>C[1] and pct(A[1],C[1])<=.03:
                ls=[x for x in l if A[0]<x[0]<B[0]]; rs=[x for x in l if B[0]<x[0]<C[0]]
                if ls and rs:
                    n=(ls[-1][1]+rs[-1][1])/2
                    if price<n:
                        ht=B[1]-n
                        add("Head & Shoulders","SELL",price,max(C[1],rs[-1][1]),n-ht,92,"Head above both shoulders; neckline broken.")
    if len(l)>=2:
        a,b=l[-2],l[-1]
        mids=[x for x in h if a[0]<x[0]<b[0]]
        if mids and pct(a[1],b[1])<=.02:
            n=mids[-1][1]
            if price>n:
                height=n-min(a[1],b[1])
                add("Double Bottom","BUY",price,min(a[1],b[1]),n+height,88,f"Two lows within 2%; neckline {n:.2f} broken.")
        if len(l)>=3:
            A,B,C=l[-3],l[-2],l[-1]
            if B[1]<A[1] and B[1]<C[1] and pct(A[1],C[1])<=.03:
                ls=[x for x in h if A[0]<x[0]<B[0]]; rs=[x for x in h if B[0]<x[0]<C[0]]
                if ls and rs:
                    n=(ls[-1][1]+rs[-1][1])/2
                    if price>n:
                        ht=n-B[1]
                        add("Inverse Head & Shoulders","BUY",price,min(C[1],rs[-1][1]),n+ht,92,"Head below both shoulders; neckline broken.")
    if len(h)>=2 and len(l)>=2:
        H1,H2=h[-2],h[-1]; L1,L2=l[-2],l[-1]
        if pct(H1[1],H2[1])<=.02 and L2[1]>L1[1] and price>H2[1]:
            height=H2[1]-min(L1[1],L2[1]); add("Ascending Triangle","BUY",price,min(L1[1],L2[1]),price+height,84,"Flat resistance, rising lows, upside breakout.")
        if pct(L1[1],L2[1])<=.02 and H2[1]<H1[1] and price<L2[1]:
            height=max(H1[1],H2[1])-L2[1]; add("Descending Triangle","SELL",price,max(H1[1],H2[1]),price-height,84,"Flat support, falling highs, downside breakout.")
    xs=cs[-25:]; early=cs[-25:-12]; late=cs[-12:]
    if len(early)>=2 and len(late)>=2:
        eh=max(x["high"] for x in early); el=min(x["low"] for x in early)
        lh=max(x["high"] for x in late); ll=min(x["low"] for x in late)
        if lh<eh and ll>el and price>lh: add("Symmetrical Triangle","BUY",price,el,price+(eh-el),78,"Converging range with upside breakout.")
        if lh<eh and ll>el and price<ll: add("Symmetrical Triangle","SELL",price,eh,price-(eh-el),78,"Converging range with downside breakout.")
        impulse_start=cs[max(0,len(cs)-20)]["close"]; last_close=cs[-1]["close"]; pole=(last_close-impulse_start)/max(abs(impulse_start),1e-9)
        if pole>.012 and ll>el and price>lh: add("Bullish Flag","BUY",price,el,price+(last_close-impulse_start),82,"Bullish pole + tight consolidation + upside break.")
        if pole<-.012 and lh<eh and price<ll: add("Bearish Flag","SELL",price,eh,price-(abs(last_close-impulse_start)),82,"Bearish pole + consolidation + downside break.")
        us=(lh-eh)/11; ls=(ll-el)/11
        rh=max(x["high"] for x in xs); rl=min(x["low"] for x in xs)
        if us<0 and ls<0 and price>lh: add("Falling Wedge","BUY",price,rl,price+(rh-rl),80,"Downward wedge boundaries + upper break.")
        if us>0 and ls>0 and price<ll: add("Rising Wedge","SELL",price,rh,price-(rh-rl),80,"Upward wedge boundaries + lower break.")
    return sorted(out,key=lambda x:x["confidence"],reverse=True)

def book_analysis(cs,symbol,tf):
    current=cs[-1]; pp=pivots(cs[-2]); pats=book_patterns(cs); best=pats[0] if pats else None
    return {"symbolCode":symbol,"timeFrame":tf,"price":current["close"],"trend":trend(cs),"atr":atr(cs),"pivot":pp,
            "range":{"high":max(x["high"] for x in cs[-40:]),"low":min(x["low"] for x in cs[-40:])},
            "patterns":pats,"signal":best["direction"] if best else "WAIT","bestPattern":best["name"] if best else "No qualifying book pattern",
            "entry":best["entry"] if best else current["close"],"sl":best["sl"] if best else None,"tp":best["tp"] if best else None,
            "rr":(abs(best["tp"]-best["entry"])/abs(best["entry"]-best["sl"])) if best and abs(best["entry"]-best["sl"]) else None,
            "source":"SIMPLE TRADING Book v1 pattern logic"}

BOOK_NAMES=["Double Top","Double Bottom","Head & Shoulders","Inverse Head & Shoulders","Ascending Triangle","Descending Triangle","Symmetrical Triangle","Bullish Flag","Bearish Flag","Falling/Rising Wedge"]

def ai_second_opinion(payload):
    if not openai: return {"available":False,"error":"OPENAI_API_KEY is not configured."}
    global _ai_cache
    now=time.time()
    if _ai_cache["data"] is not None and now-_ai_cache["at"]<30: return _ai_cache["data"]
    system="""You are the SECOND-OPINION AI validator for a live XAUUSD system.
PRIMARY SOURCE: SIMPLE TRADING Book v1. A SECONDARY ENGINE is supplied from another
uploaded XAUUSD analysis website. Do not invent strategies outside the supplied engines.
Inspect the supplied OHLC candles and BOTH deterministic engines.
Validate pattern geometry, breakout, trend, support/resistance, pivots, entry, SL, TP and R:R.
Return BUY, SELL or WAIT. Prefer WAIT on conflict or insufficient evidence.
For FINAL consensus, do not choose a side that is contradicted by both deterministic engines.
Return strict JSON with:
signal, confidence, pattern, summary, reasons, risks, market_bias, entry, stop_loss,
take_profit_1, take_profit_2, risk_reward, invalidation, book_signal, secondary_signal,
consensus.
"""
    resp=openai.responses.create(model=OPENAI_MODEL,input=[{"role":"system","content":system},{"role":"user","content":json.dumps(payload)}])
    text=resp.output_text.strip()
    try: data=json.loads(text)
    except: raise RuntimeError("OpenAI returned invalid JSON")
    data["available"]=True; data["model"]=OPENAI_MODEL
    _ai_cache={"at":now,"data":data}
    return data

def final_decision(book,secondary,ai):
    b=book.get("signal","WAIT"); s=secondary.get("signal","NO TRADE"); s2="WAIT" if s in ("NO TRADE","") else s
    a=(ai or {}).get("signal","WAIT")
    if b!="WAIT" and b==s2==a:
        status="CONFIRMED"; final=b
    elif b=="WAIT" and s2!="WAIT" and s2==a:
        status="SECONDARY_CONFIRMED"; final=s2
    elif s2=="WAIT" and b!="WAIT" and b==a:
        status="BOOK_CONFIRMED"; final=b
    elif b=="WAIT" and s2=="WAIT" and a=="WAIT":
        status="NO_SETUP"; final="WAIT"
    else:
        status="CONFLICT"; final="WAIT"
    confs=[]
    if b!="WAIT" and book.get("patterns"): confs.append(float(book["patterns"][0].get("confidence",0)))
    if s2!="WAIT" and secondary.get("all_signals"): 
        try: confs.append(float(max(x.get("rr",0) for x in secondary["all_signals"]))*25)
        except: pass
    if isinstance((ai or {}).get("confidence"),(int,float)): confs.append(float(ai["confidence"]))
    return {"finalSignal":final,"decisionStatus":status,"bookSignal":b,"secondarySignal":s2,"openAISecondOpinion":a,
            "finalConfidence":round(float(np.mean(confs))) if confs else 0,
            "agreementCount":sum(x==final and final!="WAIT" for x in [b,s2,a]),
            "allThreeAgree":final!="WAIT" and b==s2==a}


@app.websocket("/ws/price")
async def ws_price(websocket: WebSocket):
    await websocket.accept()
    symbol = websocket.query_params.get("symbolCode", "XAUUSD")
    timeframe = websocket.query_params.get("timeFrame", "M5")
    if not REALMARKET_API_KEY:
        await websocket.send_json({"type":"error","error":"REALMARKET_API_KEY is not configured on Railway."})
        await websocket.close(code=1011)
        return
    url = f"{WS_BASE}?apiKey={REALMARKET_API_KEY}&symbolCode={symbol}&timeFrame={timeframe}"
    try:
        async with websockets.connect(url, ping_interval=20, ping_timeout=20, close_timeout=5) as upstream:
            async for message in upstream:
                try:
                    raw=json.loads(message)
                    if isinstance(raw, dict):
                        try:
                            candle=norm(raw)
                            await websocket.send_json({"type":"candle","candle":candle,"raw":raw})
                        except Exception:
                            await websocket.send_json({"type":"tick","raw":raw})
                    else:
                        await websocket.send_json({"type":"raw","raw":raw})
                except Exception as exc:
                    await websocket.send_json({"type":"error","error":str(exc)})
    except WebSocketDisconnect:
        return
    except Exception as exc:
        try: await websocket.send_json({"type":"error","error":str(exc)})
        except Exception: pass
        try: await websocket.close(code=1011)
        except Exception: pass

@app.get("/api/health")
def health():
    return {"ok":True,"provider":"RealMarketAPI","realMarketConfigured":bool(REALMARKET_API_KEY),"openAIConfigured":bool(OPENAI_API_KEY),"model":OPENAI_MODEL}

@app.get("/api/candles")
def candles(symbolCode:str="XAUUSD",timeFrame:str="M5"):
    try:return {"symbolCode":symbolCode,"timeFrame":timeFrame,"candles":get_candles(symbolCode,timeFrame)}
    except Exception as e: raise HTTPException(502,str(e))

@app.get("/api/analyze")
def analyze(symbolCode:str="XAUUSD",timeFrame:str="M5"):
    try:
        cs=get_candles(symbolCode,timeFrame)
        if len(cs)<30: raise RuntimeError("Not enough candles")
        book=book_analysis(cs,symbolCode,timeFrame)
        dfd=candles_df(cs)
        secondary=secondary_latest(dfd,Config())
        # Normalize secondary response for JSON
        secondary["signal"]="WAIT" if secondary.get("signal")=="NO TRADE" else secondary.get("signal","WAIT")
        snap={
          "symbol":symbolCode,"timeframe":timeFrame,"current_price":cs[-1]["close"],"trend":trend(cs),"atr":atr(cs),
          "pivot":book["pivot"],"range":book["range"],
          "book_engine":{"signal":book["signal"],"best_pattern":book["bestPattern"],"patterns":book["patterns"]},
          "secondary_engine":{"signal":secondary["signal"],"strategy":secondary.get("strategy"),"entry":secondary.get("entry"),
             "sl":secondary.get("sl"),"tp":secondary.get("tp"),"rr":secondary.get("rr"),"reason":secondary.get("reason"),
             "all_signals":secondary.get("all_signals",[])},
          "candles":cs[-120:]
        }
        ai=ai_second_opinion(snap) if openai else None
        decision=final_decision(book,secondary,ai)
        # choose levels from agreeing engine/AI, fallback book
        level_source=ai if ai and ai.get("signal")!="WAIT" else (book if decision["bookSignal"]!="WAIT" else secondary)
        return {"symbolCode":symbolCode,"timeFrame":timeFrame,"price":cs[-1]["close"],"trend":trend(cs),"atr":atr(cs),
                "pivot":book["pivot"],"range":book["range"],"candles":cs,"book":book,
                "secondary":secondary,"ai":ai,"decision":decision,"updatedAt":datetime.now(timezone.utc).isoformat(),
                "entry":level_source.get("entry"),"sl":level_source.get("sl",level_source.get("stop_loss")),
                "tp":level_source.get("tp",level_source.get("take_profit_1"))}
    except Exception as e: raise HTTPException(502,str(e))

@app.get("/api/price")
def price(symbolCode:str="XAUUSD",timeFrame:str="M5"):
    try:return api_get("/api/v1/price",{"symbolCode":symbolCode,"timeFrame":timeFrame})
    except Exception as e: raise HTTPException(502,str(e))

app.mount("/",StaticFiles(directory="../frontend",html=True),name="frontend")
