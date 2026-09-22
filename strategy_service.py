"""Authenticated API, durable per-candle decisions and History/MT5 outbox."""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Float, String, Text, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

import main as core
import strategy_suite as suite

router = APIRouter(prefix="/api/v1/strategies", tags=["Independent strategies"])
LOCKS = {mid: asyncio.Lock() for mid in suite.MODULES}
AI_SLOTS = asyncio.Semaphore(3)
TRANSPORT = os.getenv("MT5_EXECUTION_TRANSPORT", "legacy").strip().lower()
if TRANSPORT not in {"gateway", "legacy"}:
    raise RuntimeError("MT5_EXECUTION_TRANSPORT must be gateway or legacy")


class StrategyConfig(core.Base):
    __tablename__ = "strategy_suite_config"
    module_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    interval: Mapped[str] = mapped_column(String(20))
    target_rr: Mapped[float] = mapped_column(Float, default=2.0)


class StrategyEvent(core.Base):
    __tablename__ = "strategy_suite_events"
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[str] = mapped_column(Text)


class StrategyOutbox(core.Base):
    __tablename__ = "strategy_suite_outbox"
    signal_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    payload: Mapped[str] = mapped_column(Text)
    legacy_claimed: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_epoch: Mapped[float] = mapped_column(Float, index=True)


core.Base.metadata.create_all(core.engine)


def config(mid, session):
    m = suite.MODULES.get(mid)
    if not m:
        raise HTTPException(404, "Unknown strategy")
    row = session.get(StrategyConfig, mid)
    return {"module_id": mid, **m, "interval": row.interval if row else m["interval"], "target_rr": row.target_rr if row else 2.0, "min_rr": 1.0}


def _now():
    return datetime.now(timezone.utc).timestamp()


def _event_id(mid, tf, candle):
    return hashlib.sha256(f"{suite.VERSION}|{mid}|XAU/USD|{tf}|{candle}".encode()).hexdigest()


def _uid(user_id, event_id):
    return "SX9-" + hashlib.sha256(f"{user_id}|{event_id}".encode()).hexdigest()[:32]


def _ai_pass(ai, direction):
    try:
        conf, agreement = float(ai.get("confidence", 0)), float(ai.get("agreement", 0))
        return (ai.get("mode") in core.AI_PROVIDER_PROFILE and ai.get("validation") is True
                and ai.get("signal") == direction and math.isfinite(conf) and math.isfinite(agreement)
                and 85 <= conf <= 100 and 70 <= agreement <= 100 and ai.get("risk_flags") == [])
    except (TypeError, ValueError):
        return False


async def validate_ai(candidate):
    """A live AI veto only: it cannot edit levels or borrow another module's vote."""
    prompt = (
        "Validate ONLY this independent SignalX strategy candidate and its supplied evidence. "
        "Do not combine signals from other strategies. Do not invent data, prices, news or profitability. "
        "All candles are closed. Test the stated rules, direction and Entry/SL/TP geometry. "
        "RR is reward/risk; any finite RR >= 1 is allowed, but implausible or blocked targets must be vetoed. "
        "Return JSON only: signal BUY/SELL/WAIT, validation boolean, confidence 0-100, agreement 0-100, "
        "risk_flags array (empty only if no blocking issues), reasoning string. "
        "Missing evidence or conflicting rules requires WAIT and validation=false. "
        "Never describe confidence as an observed win rate.\n" + json.dumps(candidate, allow_nan=False)
    )
    try:
        async with AI_SLOTS:
            raw, provider = await asyncio.wait_for(core.ai_json_completion(prompt), timeout=45)
        ai = json.loads(raw)
        if not isinstance(ai, dict):
            raise ValueError("INVALID_AI_JSON")
        ai["mode"] = provider
        return ai
    except Exception:
        return {"mode": "unavailable", "signal": "WAIT", "validation": False, "confidence": 0,
                "agreement": 0, "risk_flags": ["AI_UNAVAILABLE"], "reasoning": "Live AI tasdig‘i olinmadi."}


def blocked(candidate, reason):
    return {**candidate, "signal": "WAIT", "entry": None, "stop_loss": None, "take_profit": [],
            "risk_reward": None, "state": reason, "reason": reason, "auto_trade_eligible": False}


async def evaluate(mid):
    async with LOCKS[mid]:
        with core.SessionLocal() as db:
            cfg = config(mid, db)
        tf = cfg["interval"]
        htf = "30min" if mid == "ict-ai-pro" else {"5min":"30min", "15min":"1h", "30min":"4h", "1h":"4h", "4h":"1day"}[tf]
        now = _now()
        base = {**suite.wait(mid, "WAIT"), "interval": tf, "higher_interval": htf, "target_rr": cfg["target_rr"],
                "symbol": "XAU/USD", "generated_at": datetime.fromtimestamp(now, timezone.utc).isoformat()}
        if not core.market_gate_status("XAU/USD").get("open"):
            return blocked(base, "MARKET_CLOSED")
        try:
            raw, high = await asyncio.gather(core.get_market_snapshot("XAU/USD",tf,260), core.get_market_snapshot("XAU/USD",htf,260))
            for snap in (raw, high):
                if snap.get("mode") != "live" or snap.get("provider") not in core.STRICT_LIVE_MARKET_PROVIDERS:
                    raise ValueError("LIVE_PROVIDER_REQUIRED")
            cs = suite.closed_candles(raw["candles"],core.TIMEFRAME_SECONDS[tf],now)
            hs = suite.closed_candles(high["candles"],core.TIMEFRAME_SECONDS[htf],now)
            live_price = float(raw["candles"][-1]["close"])
        except Exception as exc:
            # A data failure is not a per-candle strategy decision; retry next cycle.
            return blocked(base, str(exc) if isinstance(exc,ValueError) else "LIVE_DATA_UNAVAILABLE")
        candle = str(cs[-1]["time"])
        eid = _event_id(mid,tf,candle)
        current = {"live_price": live_price, "provider": raw["provider"], "higher_provider": high["provider"],
                   "feed_checked_at": now, "candles": cs[-70:]}
        with core.SessionLocal() as db:
            row = db.get(StrategyEvent,eid)
            if row:
                saved=json.loads(row.payload)
                result={**saved, **current}
                if result.get("signal") in {"BUY","SELL"} and now >= result.get("expires_epoch",0):
                    return blocked(result,"SETUP_EXPIRED")
                return result
            base.update(candle_time=candle,event_id=eid,**current)
            # Unique DB claim isolates concurrent workers and survives restarts.
            row=StrategyEvent(event_id=eid,payload=json.dumps({k:v for k,v in blocked(base,"EVALUATING").items() if k!="candles"}))
            db.add(row)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                return {**json.loads(db.get(StrategyEvent,eid).payload), **current}
        try:
            result={**base, **suite.analyze(mid,cs,hs,float(cfg["target_rr"]))}
            result.update(candle_time=candle,event_id=eid,interval=tf,
                          expires_epoch=min(now+300,cs[-1]["time"]+2*core.TIMEFRAME_SECONDS[tf]),
                          recent_candles=cs[-10:])
            if result["signal"] in {"BUY","SELL"}:
                ai=await validate_ai(result)
                json.dumps(ai,allow_nan=False)  # Malformed AI JSON never reaches a response or DB.
                result["ai_validation"]=ai
                passed=_ai_pass(ai,result["signal"])
                result["ai_gate"]={"passed":passed,"required":True,"minimum_confidence":85,"minimum_agreement":70}
                if passed:
                    result.update(state="READY",auto_trade_eligible=True)
                else:
                    result=blocked(result,"AI_NOT_CONFIRMED")
        except Exception:
            result=blocked(base,"EVALUATION_FAILED")
        with core.SessionLocal() as db:
            row=db.get(StrategyEvent,eid)
            row.payload=json.dumps({k:v for k,v in result.items() if k!="candles"},allow_nan=False)
            db.commit()
        return result


def persist(session, user_id, result):
    """An immutable, separate row for each user/module/timeframe/closed candle."""
    if result.get("signal") not in {"BUY","SELL"} or result.get("state") != "READY":
        return None, False
    if result.get("module_id") not in suite.MODULES or result.get("source") != suite.MODULES[result["module_id"]]["source"]:
        return None, False
    rr=suite.reward_risk(result["signal"],result.get("entry"),result.get("stop_loss"),result.get("take_profit",[]))
    if rr is None or rr < 1-1e-8 or not _ai_pass(result.get("ai_validation",{}),result["signal"]):
        return None, False
    uid=_uid(user_id,result["event_id"])
    row=session.scalar(select(core.SignalHistory).where(core.SignalHistory.signal_uid==uid))
    if row:
        return row,False
    payload={**result,"candles":result.get("recent_candles",[]),
             "confidence_at_entry":result["ai_validation"]["confidence"],"signal_strength":"RULES_AND_AI",
             "setup":{"entry":result["entry"],"stop_loss":result["stop_loss"],"take_profit":result["take_profit"]},
             "execution_gate":{"auto_trade":True,"risk_reward":rr,"rr_min":1.0,"state":"READY"},
             "execution":{"state":"NOT_SENT","transport":TRANSPORT},
             "expires_at":datetime.fromtimestamp(result["expires_epoch"],timezone.utc).isoformat()}
    row=core.SignalHistory(user_id=user_id,source=result["source"],symbol="XAU/USD",interval=result["interval"],
        direction=result["signal"],headline=result["strategy"],price=result["entry"],payload=json.dumps(payload,allow_nan=False),
        candle_time=result["candle_time"],signal_uid=uid,entry_price=result["entry"],stop_loss=result["stop_loss"],
        take_profit_1=result["take_profit"][0],take_profit_2=None,risk_reward=rr,
        status="ACTIVE",outcome="OPEN",signal_score=result["ai_validation"]["confidence"],signal_strength="RULES_AND_AI")
    session.add(row)
    try:
        session.commit()
        return row,True
    except IntegrityError:
        session.rollback()
        row=session.scalar(select(core.SignalHistory).where(core.SignalHistory.user_id==user_id,
            core.SignalHistory.source==result["source"],core.SignalHistory.symbol=="XAU/USD",
            core.SignalHistory.interval==result["interval"],core.SignalHistory.candle_time==result["candle_time"]))
        return row,False


def authorized_order(source, direction, entry, sl, tp, signal_id, interval=None, candle_time=None):
    """Queue defense-in-depth: only a committed server-validated snapshot can trade."""
    if source not in suite.SOURCES or not signal_id or not tp:
        return False
    with core.SessionLocal() as db:
        row=db.scalar(select(core.SignalHistory).where(core.SignalHistory.signal_uid==signal_id))
        if row is None or row.source!=source or row.direction!=direction or row.outcome!="OPEN":
            return False
        if interval is not None and row.interval!=interval or candle_time is not None and str(row.candle_time)!=str(candle_time):
            return False
        x=json.loads(row.payload)
        if x.get("contract_version")!=suite.VERSION or not _ai_pass(x.get("ai_validation",{}),direction):
            return False
        if _now()>=x.get("expires_epoch",0) or not core.market_gate_status("XAU/USD").get("open"):
            return False
        return (row.entry_price==entry and row.stop_loss==sl and row.take_profit_1==tp[0]
                and x.get("entry")==entry and x.get("stop_loss")==sl and x.get("take_profit")==tp
                and x.get("auto_trade_eligible") is True)


async def dispatch(session, row, result):
    if not row or not core.MT5_AUTO_TRADING or not core.AUTO_ENTRY_ENABLED:
        return None
    if session.get(StrategyOutbox,row.signal_uid):
        return None
    try:
        live=await core.get_market_snapshot("XAU/USD",result["interval"],260)
        if live.get("mode")!="live" or live.get("provider") not in core.STRICT_LIVE_MARKET_PROVIDERS:
            return None
        suite.closed_candles(live["candles"],core.TIMEFRAME_SECONDS[result["interval"]],_now())
        current=float(live["candles"][-1]["close"])
    except Exception:
        return None
    rr=suite.reward_risk(result["signal"],current,result["stop_loss"],result["take_profit"])
    if rr is None or rr < 1-1e-8 or abs(current-result["entry"])>.35*result.get("atr",0) or _now()>=result["expires_epoch"]:
        return None
    order=core._queue_autotrade_order(symbol="XAU/USD",source=row.source,interval=row.interval,
        direction=row.direction,entry=row.entry_price,sl=row.stop_loss,tp=result["take_profit"],
        volume=core.MT5_LOT_SIZE,confidence=row.signal_score,candle_time=row.candle_time,
        risk_reward=row.risk_reward,expires_at=datetime.fromtimestamp(result["expires_epoch"],timezone.utc).isoformat(),signal_id=row.signal_uid)
    if not order:
        return None
    session.add(StrategyOutbox(signal_id=row.signal_uid,payload=json.dumps(order),expires_epoch=result["expires_epoch"]))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
    return order


def restore_outbox():
    """Gateway dedup is persistent. Ambiguous legacy delivery is never replayed."""
    with core.SessionLocal() as db:
        for row in db.scalars(select(StrategyOutbox).where(StrategyOutbox.expires_epoch>_now(),StrategyOutbox.legacy_claimed==False)):
            q=json.loads(row.payload)
            if datetime.fromisoformat(q["expires_at"]).timestamp() <= _now():
                continue
            if not authorized_order(q["source"],q["direction"],q["entry"],q["sl"],q["tp"],q["signal_id"]):
                continue
            if not any(x["id"]==q["id"] for x in core.MT5_ORDER_QUEUE):
                core.MT5_ORDER_QUEUE.append(q)


def claim_legacy(signal_id):
    # A claim is written before returning an order. No ambiguous restart replay.
    with core.SessionLocal() as db:
        result=db.execute(update(StrategyOutbox).where(StrategyOutbox.signal_id==signal_id,
            StrategyOutbox.legacy_claimed==False,StrategyOutbox.expires_epoch>_now()).values(legacy_claimed=True))
        db.commit()
        return result.rowcount==1


async def scan(session, admin):
    restore_outbox()
    results=await asyncio.gather(*(evaluate(mid) for mid in suite.MODULES),return_exceptions=True)
    user_ids=list(session.scalars(select(core.User.id)))
    saved,queued,errors=0,0,[]
    for mid,x in zip(suite.MODULES,results):
        if isinstance(x,Exception):
            errors.append({"module_id":mid,"state":"SCAN_FAILED"})
            continue
        owner_row=None
        for uid in user_ids:
            row,created=persist(session,uid,x)
            saved+=int(created)
            if uid==admin.id: owner_row=row
        if owner_row and await dispatch(session,owner_row,x): queued+=1
    if TRANSPORT=="gateway":
        from mt5_account_gateway import _sync_core_queue
        _sync_core_queue(session)
    return {"enabled":True,"count":saved,"queued":queued,"mode":"independent_strategies", "errors":errors,
            "symbols":["XAU/USD"],"active_sources":list(m["source"] for m in suite.MODULES.values()),
            "user_id":admin.id,"rr_min":1.0,"transport":TRANSPORT}


class ConfigBody(BaseModel):
    interval: str
    target_rr: float = Field(ge=1,allow_inf_nan=False)


@router.get("")
async def catalog(authorization: str|None=Header(default=None),session=Depends(core.db)):
    user=core.current_user(authorization,session)
    return {"items":[config(mid,session) for mid in suite.MODULES],"can_configure":core.is_admin_user(user),
            "rr_min":1.0,"rr_max":None,"transport":TRANSPORT,"autotrade_enabled":core.MT5_AUTO_TRADING and core.AUTO_ENTRY_ENABLED}


@router.put("/{mid}/config")
async def configure(mid: str,body: ConfigBody,authorization: str|None=Header(default=None),session=Depends(core.db)):
    core.require_admin(authorization,session)
    cfg=config(mid,session)
    if body.interval not in suite.INTERVALS or (mid=="ict-ai-pro" and body.interval!="5min"):
        raise HTTPException(422,"Invalid timeframe; ICT AI Pro uses M5 with M30 context")
    row=session.get(StrategyConfig,mid)
    if not row:
        row=StrategyConfig(module_id=mid,interval=body.interval,target_rr=body.target_rr)
        session.add(row)
    else:
        row.interval,row.target_rr=body.interval,body.target_rr
    session.commit()
    return {"ok":True,"config":config(mid,session),"note":"Previously evaluated candles stay unchanged; RR applies to the next new candle."}


@router.get("/{mid}")
async def analysis(mid: str,authorization: str|None=Header(default=None),session=Depends(core.db)):
    core.current_user(authorization,session)
    config(mid,session)
    return await evaluate(mid)


@router.post("/{mid}/record")
async def record(mid: str,authorization: str|None=Header(default=None),session=Depends(core.db),event_id: str|None=None):
    user=core.current_user(authorization,session)
    config(mid,session)
    result=await evaluate(mid)
    if event_id is not None and result.get("event_id")!=event_id:
        return {"saved":False,"queued":False,"reason":"STALE_CLIENT_EVENT","source":result["source"]}
    row,created=persist(session,user.id,result)
    order=await dispatch(session,row,result) if row and core.is_admin_user(user) else None
    return {"saved":bool(row),"created":created,"signal_id":row.signal_uid if row else None,
            "queued":bool(order),"source":result["source"],"reason":result["state"]}
