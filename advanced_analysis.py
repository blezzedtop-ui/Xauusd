from __future__ import annotations
import json
import os
from typing import Any
import numpy as np
import pandas as pd

from price_action_10_strategies import Config, analyze as secondary_analyze, latest_signal as secondary_latest

BOOK_NAMES = [
    "Double Top", "Double Bottom", "Head & Shoulders", "Inverse Head & Shoulders",
    "Ascending Triangle", "Descending Triangle", "Symmetrical Triangle",
    "Bullish Flag", "Bearish Flag", "Falling/Rising Wedge"
]

def pct(a: float, b: float) -> float:
    return abs(a-b) / max((abs(a)+abs(b))/2, 1e-12)

def local_extrema(cs: list[dict], look: int = 2):
    highs, lows = [], []
    for i in range(look, len(cs)-look):
        hi = all(cs[i]["high"] >= cs[i-j]["high"] and cs[i]["high"] >= cs[i+j]["high"] for j in range(1, look+1))
        lo = all(cs[i]["low"] <= cs[i-j]["low"] and cs[i]["low"] <= cs[i+j]["low"] for j in range(1, look+1))
        if hi: highs.append((i, float(cs[i]["high"])))
        if lo: lows.append((i, float(cs[i]["low"])))
    return highs, lows

def atr(cs: list[dict], p: int = 14) -> float:
    if len(cs) <= p: return 0.0
    tr=[]
    for i in range(1,len(cs)):
        tr.append(max(cs[i]["high"]-cs[i]["low"], abs(cs[i]["high"]-cs[i-1]["close"]), abs(cs[i]["low"]-cs[i-1]["close"])))
    return float(np.mean(tr[-p:]))

def trend(cs: list[dict]) -> str:
    if len(cs)<20: return "NEUTRAL"
    closes=np.array([x["close"] for x in cs])
    fast=float(np.mean(closes[-8:])); slow=float(np.mean(closes[-20:]))
    if fast>slow*1.001: return "BULLISH"
    if fast<slow*0.999: return "BEARISH"
    return "NEUTRAL"

def pivots(c: dict) -> dict:
    p=(c["high"]+c["low"]+c["close"])/3
    return {"pivot":p,"r1":2*p-c["low"],"r2":p+(c["high"]-c["low"]),"r3":c["high"]+2*(p-c["low"]),
            "s1":2*p-c["high"],"s2":p-(c["high"]-c["low"]),"s3":c["low"]-2*(c["high"]-p)}

def structure(cs: list[dict]) -> dict:
    highs,lows=local_extrema(cs,2)
    h=highs[-4:]; l=lows[-4:]
    labels=[]
    for k in range(1,len(h)):
        labels.append("HH" if h[k][1]>h[k-1][1] else "LH")
    for k in range(1,len(l)):
        labels.append("HL" if l[k][1]>l[k-1][1] else "LL")
    if len(h)>=2 and len(l)>=2:
        hh=h[-1][1]>h[-2][1]; hl=l[-1][1]>l[-2][1]
        lh=h[-1][1]<h[-2][1]; ll=l[-1][1]<l[-2][1]
        if hh and hl: state="BULLISH_STRUCTURE"
        elif lh and ll: state="BEARISH_STRUCTURE"
        else: state="RANGE/TRANSITION"
    else: state="INSUFFICIENT_SWINGS"
    return {"state":state,"recent_highs":[{"index":i,"price":p} for i,p in h],"recent_lows":[{"index":i,"price":p} for i,p in l],"labels":labels}

def zones(cs: list[dict], max_zones: int=4) -> dict:
    highs,lows=local_extrema(cs,2)
    a=max(atr(cs),1e-9)
    clusters=[]
    for typ, arr in (("resistance",highs),("support",lows)):
        vals=[p for _,p in arr[-12:]]
        used=[]
        for p in vals:
            found=None
            for z in used:
                if abs(p-z["center"]) <= 0.35*a:
                    z["prices"].append(p); z["center"]=float(np.mean(z["prices"])); found=z; break
            if found is None: used.append({"center":p,"prices":[p]})
        for z in used:
            half=max(0.18*a, (max(z["prices"])-min(z["prices"]))/2 if len(z["prices"])>1 else 0.18*a)
            clusters.append({"type":typ,"low":z["center"]-half,"high":z["center"]+half,"center":z["center"],"touches":len(z["prices"])})
    res=sorted([x for x in clusters if x["type"]=="resistance"], key=lambda x:x["center"], reverse=True)[:max_zones]
    sup=sorted([x for x in clusters if x["type"]=="support"], key=lambda x:x["center"], reverse=True)[:max_zones]
    return {"support":sup,"resistance":res}

def book_patterns(cs: list[dict]) -> list[dict]:
    out=[]; highs,lows=local_extrema(cs,2); price=cs[-1]["close"]
    h=highs[-6:]; l=lows[-6:]
    def add(name,direction,entry,sl,tp,confidence,why):
        if all(np.isfinite(v) for v in [entry,sl,tp]) and abs(entry-sl)>0:
            out.append({"name":name,"direction":direction,"entry":float(entry),"sl":float(sl),"tp":float(tp),"confidence":confidence,"why":why})
    if len(h)>=2:
        a,b=h[-2],h[-1]; mids=[x for x in l if a[0]<x[0]<b[0]]
        if mids and pct(a[1],b[1])<=.02 and price<mids[-1][1]:
            n=mids[-1][1]; height=max(a[1],b[1])-n; add("Double Top","SELL",price,max(a[1],b[1]),n-height,88,f"Two highs near the same level; neckline {n:.2f} broken.")
        if len(h)>=3:
            A,B,C=h[-3],h[-2],h[-1]
            if B[1]>A[1] and B[1]>C[1] and pct(A[1],C[1])<=.03:
                ls=[x for x in l if A[0]<x[0]<B[0]]; rs=[x for x in l if B[0]<x[0]<C[0]]
                if ls and rs and price<(ls[-1][1]+rs[-1][1])/2:
                    n=(ls[-1][1]+rs[-1][1])/2; add("Head & Shoulders","SELL",price,max(C[1],rs[-1][1]),n-(B[1]-n),92,"Head above shoulders; neckline broken.")
    if len(l)>=2:
        a,b=l[-2],l[-1]; mids=[x for x in h if a[0]<x[0]<b[0]]
        if mids and pct(a[1],b[1])<=.02 and price>mids[-1][1]:
            n=mids[-1][1]; height=n-min(a[1],b[1]); add("Double Bottom","BUY",price,min(a[1],b[1]),n+height,88,f"Two lows near the same level; neckline {n:.2f} broken.")
        if len(l)>=3:
            A,B,C=l[-3],l[-2],l[-1]
            if B[1]<A[1] and B[1]<C[1] and pct(A[1],C[1])<=.03:
                ls=[x for x in h if A[0]<x[0]<B[0]]; rs=[x for x in h if B[0]<x[0]<C[0]]
                if ls and rs and price>(ls[-1][1]+rs[-1][1])/2:
                    n=(ls[-1][1]+rs[-1][1])/2; add("Inverse Head & Shoulders","BUY",price,min(C[1],rs[-1][1]),n+(n-B[1]),92,"Head below shoulders; neckline broken.")
    if len(h)>=2 and len(l)>=2:
        H1,H2=h[-2],h[-1]; L1,L2=l[-2],l[-1]
        if pct(H1[1],H2[1])<=.02 and L2[1]>L1[1] and price>H2[1]: add("Ascending Triangle","BUY",price,min(L1[1],L2[1]),price+(H2[1]-min(L1[1],L2[1])),84,"Flat resistance with rising lows and upside breakout.")
        if pct(L1[1],L2[1])<=.02 and H2[1]<H1[1] and price<L2[1]: add("Descending Triangle","SELL",price,max(H1[1],H2[1]),price-(max(H1[1],H2[1])-L2[1]),84,"Flat support with falling highs and downside breakout.")
    xs=cs[-25:]; early=cs[-25:-12]; late=cs[-12:]
    if len(early)>=2 and len(late)>=2:
        eh=max(x["high"] for x in early); el=min(x["low"] for x in early); lh=max(x["high"] for x in late); ll=min(x["low"] for x in late)
        if lh<eh and ll>el and price>lh: add("Symmetrical Triangle","BUY",price,el,price+(eh-el),78,"Converging range with upside breakout.")
        if lh<eh and ll>el and price<ll: add("Symmetrical Triangle","SELL",price,eh,price-(eh-el),78,"Converging range with downside breakout.")
        start=cs[max(0,len(cs)-20)]["close"]; last=cs[-1]["close"]; pole=(last-start)/max(abs(start),1e-9)
        if pole>.012 and ll>el and price>lh: add("Bullish Flag","BUY",price,el,price+(last-start),82,"Bullish pole + consolidation + upside break.")
        if pole<-.012 and lh<eh and price<ll: add("Bearish Flag","SELL",price,eh,price-abs(last-start),82,"Bearish pole + consolidation + downside break.")
        rh=max(x["high"] for x in xs); rl=min(x["low"] for x in xs)
        if (lh-eh)<0 and (ll-el)<0 and price>lh: add("Falling Wedge","BUY",price,rl,price+(rh-rl),80,"Falling wedge boundaries + upper break.")
        if (lh-eh)>0 and (ll-el)>0 and price<ll: add("Rising Wedge","SELL",price,rh,price-(rh-rl),80,"Rising wedge boundaries + lower break.")
    return sorted(out,key=lambda x:x["confidence"],reverse=True)

def analyze_advanced(cs: list[dict], symbol: str, timeframe: str) -> dict:
    cs=sorted(cs,key=lambda x:x["time"])
    cdf=pd.DataFrame(cs,index=pd.to_datetime([x["time"] for x in cs],unit="s",utc=True))[['open','high','low','close']]
    book=book_patterns(cs); best=book[0] if book else None
    sec=secondary_latest(cdf,Config())
    sec_signal="WAIT" if sec.get("signal") in (None,"","NO TRADE") else sec.get("signal")
    st=structure(cs); z=zones(cs); pp=pivots(cs[-2]) if len(cs)>=2 else pivots(cs[-1])
    b=best["direction"] if best else "WAIT"
    if b==sec_signal and b!="WAIT": final=b; status="DETERMINISTIC_CONFIRMED"
    elif b=="WAIT" and sec_signal!="WAIT": final=sec_signal; status="SECONDARY_ONLY"
    elif sec_signal=="WAIT" and b!="WAIT": final=b; status="BOOK_ONLY"
    elif b=="WAIT" and sec_signal=="WAIT": final="WAIT"; status="NO_SETUP"
    else: final="WAIT"; status="CONFLICT"
    if st["state"]=="BULLISH_STRUCTURE" and final=="SELL": final="WAIT"; status="STRUCTURE_CONFLICT"
    if st["state"]=="BEARISH_STRUCTURE" and final=="BUY": final="WAIT"; status="STRUCTURE_CONFLICT"
    return {
      "symbol":symbol,"timeframe":timeframe,"price":cs[-1]["close"],"trend":trend(cs),"atr":atr(cs),"pivot":pp,
      "structure":st,"zones":z,"book":{"signal":b,"bestPattern":best["name"] if best else "No qualifying book pattern","patterns":book},
      "secondary":{"signal":sec_signal,"strategy":sec.get("strategy"),"entry":sec.get("entry"),"sl":sec.get("sl"),"tp":sec.get("tp"),"rr":sec.get("rr"),"reason":sec.get("reason")},
      "decision":{"finalSignal":final,"status":status,"bookSignal":b,"secondarySignal":sec_signal,"agreement":b==sec_signal and b!="WAIT"},
      "signalLevels": {"entry": (best or sec).get("entry") if (best or sec) else None,"sl":(best or sec).get("sl") if (best or sec) else None,"tp":(best or sec).get("tp") if (best or sec) else None},
      "source":"SIMPLE TRADING Book v1 + secondary 10-strategy engine + market structure"
    }
