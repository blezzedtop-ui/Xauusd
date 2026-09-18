
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, inspect, select, text
from sqlalchemy.orm import Mapped, mapped_column

import main as core

router = APIRouter(prefix="/api/v1/mt5/gateway", tags=["MT5 Account Gateway"])

PairCode = str
PAIR_TTL_MINUTES = 10
ACCOUNT_TOKEN_TTL_DAYS = 365
CLAIM_SECONDS = 30

def _utc() -> datetime:
    return datetime.now(timezone.utc)

def _as_utc(value: datetime | None) -> datetime | None:
    """Normalize SQLite/PostgreSQL datetime values to timezone-aware UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

def _hash(value: str) -> str:
    return hashlib.sha256((core.SECRET_KEY + value).encode()).hexdigest()

def _account_token() -> str:
    return "sxa_" + secrets.token_urlsafe(48)

def _user(auth: str | None, session):
    return core.current_user(auth, session)

class MT5Account(core.Base):
    __tablename__ = "mt5_accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(120), default="MT5 Account")
    broker: Mapped[str] = mapped_column(String(160), default="")
    server: Mapped[str] = mapped_column(String(200), default="")
    login: Mapped[str] = mapped_column(String(80), default="")
    account_type: Mapped[str] = mapped_column(String(20), default="demo", index=True)
    currency: Mapped[str] = mapped_column(String(20), default="USD")
    leverage: Mapped[int] = mapped_column(Integer, default=0)
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    equity: Mapped[float] = mapped_column(Float, default=0.0)
    free_margin: Mapped[float] = mapped_column(Float, default=0.0)
    margin: Mapped[float] = mapped_column(Float, default=0.0)
    trade_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    connected: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    auto_trade_enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    lot: Mapped[float] = mapped_column(Float, default=0.01)
    account_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    terminal_build: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ea_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc, onupdate=_utc)

class MTPairing(core.Base):
    __tablename__ = "mt5_pairings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc)

class MTSymbol(core.Base):
    __tablename__ = "mt5_account_symbols"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("mt5_accounts.id", ondelete="CASCADE"), index=True)
    canonical_symbol: Mapped[str] = mapped_column(String(50), index=True)
    broker_symbol: Mapped[str] = mapped_column(String(100))
    digits: Mapped[int] = mapped_column(Integer, default=2)
    point: Mapped[float] = mapped_column(Float, default=0.01)
    volume_min: Mapped[float] = mapped_column(Float, default=0.01)
    volume_step: Mapped[float] = mapped_column(Float, default=0.01)
    volume_max: Mapped[float] = mapped_column(Float, default=100.0)
    trade_mode: Mapped[str] = mapped_column(String(50), default="unknown")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc, onupdate=_utc)
    __table_args__ = (UniqueConstraint("account_id", "canonical_symbol", name="ux_mt5_account_symbol"),)

class MTOrder(core.Base):
    __tablename__ = "mt5_gateway_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("mt5_accounts.id", ondelete="CASCADE"), index=True)
    source_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    canonical_symbol: Mapped[str] = mapped_column(String(50))
    execution_symbol: Mapped[str] = mapped_column(String(100))
    direction: Mapped[str] = mapped_column(String(10))
    volume: Mapped[float] = mapped_column(Float)
    entry: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(80), default="Consensus")
    signal_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    candle_time: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True)
    claim_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    broker_ticket: Mapped[str | None] = mapped_column(String(100), nullable=True)
    broker_retcode: Mapped[str | None] = mapped_column(String(100), nullable=True)
    broker_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc, onupdate=_utc)
    __table_args__ = (UniqueConstraint("account_id", "source_fingerprint", name="ux_mt5_gateway_order"),)

def initialize_gateway_tables() -> None:
    """Create only the gateway tables after their models are registered.

    main.py creates its core tables before this module is imported, so the
    gateway must explicitly create these additive tables. This is safe for
    existing deployments because SQLAlchemy only creates missing tables.
    """
    core.Base.metadata.create_all(
        core.engine,
        tables=[
            MT5Account.__table__,
            MTPairing.__table__,
            MTSymbol.__table__,
            MTOrder.__table__,
        ],
    )
    # Backward-compatible migration for existing deployments.
    columns = {c["name"] for c in inspect(core.engine).get_columns(MT5Account.__tablename__)}
    if "lot" not in columns:
        with core.engine.begin() as conn:
            conn.execute(text("ALTER TABLE mt5_accounts ADD COLUMN lot FLOAT DEFAULT 0.01"))


class MTState(BaseModel):
    broker: str = ""
    server: str = ""
    login: str = ""
    account_type: str = "demo"
    currency: str = "USD"
    leverage: int = 0
    balance: float = 0
    equity: float = 0
    free_margin: float = 0
    margin: float = 0
    trade_allowed: bool = False
    terminal_build: str = ""
    ea_version: str = ""
    symbols: list[dict[str, Any]] = Field(default_factory=list)

class PairRequest(BaseModel):
    label: str = Field(default="MT5 Account", max_length=120)

class RegisterRequest(MTState):
    pairing_code: str = Field(min_length=6, max_length=32)

class ToggleRequest(BaseModel):
    enabled: bool

class LotRequest(BaseModel):
    lot: float = Field(default=0.01, ge=0.01, le=100.0)

class ReportRequest(BaseModel):
    order_id: int
    status: str
    broker_ticket: str = ""
    broker_retcode: str = ""
    broker_message: str = ""

def _account_dict(a: MT5Account) -> dict[str, Any]:
    last = a.last_seen_at
    if last and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    age = None if not last else max(0, int((_utc() - last).total_seconds()))
    return {
        "id": a.id, "label": a.label, "broker": a.broker, "server": a.server,
        "login": a.login, "account_type": a.account_type, "currency": a.currency,
        "leverage": a.leverage, "balance": a.balance, "equity": a.equity,
        "free_margin": a.free_margin, "margin": a.margin,
        "trade_allowed": a.trade_allowed,
        "connected": bool(a.connected and age is not None and age <= 45),
        "last_seen_seconds": age, "auto_trade_enabled": a.auto_trade_enabled, "lot": float(a.lot or 0.01),
        "terminal_build": a.terminal_build, "ea_version": a.ea_version,
    }

def _canonical(symbol: str) -> str:
    s = str(symbol or "").upper().replace("-", "").replace("_", "").replace("/", "")
    if s.startswith("XAUUSD"): return "XAU/USD"
    if s.startswith("EURUSD"): return "EUR/USD"
    if s.startswith("GBPUSD"): return "GBP/USD"
    return str(symbol or "").upper().replace("-", "/")

def _fingerprint(order: dict[str, Any], account_id: int) -> str:
    raw = json.dumps({
        "account": account_id,
        "signal": order.get("signal_id") or order.get("id"),
        "symbol": _canonical(order.get("symbol") or order.get("market")),
        "tf": order.get("interval"),
        "candle": order.get("candle_time"),
        "direction": order.get("direction"),
        "entry": order.get("entry"),
        "sl": order.get("sl") or order.get("stop_loss"),
        "tp": order.get("tp") or order.get("take_profit"),
    }, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()

def _sync_core_queue(session):
    queue = list(getattr(core, "MT5_ORDER_QUEUE", []) or [])
    accounts = list(session.scalars(select(MT5Account).where(MT5Account.auto_trade_enabled == True)))
    created = 0
    for account in accounts:
        for o in queue:
            if str(o.get("interval") or "").lower() in {"1m", "1min", "m1"}:
                continue
            direction = str(o.get("direction") or "").upper()
            if direction not in {"BUY", "SELL"}:
                continue
            canonical = _canonical(o.get("symbol") or "XAU/USD")
            mapping = session.scalar(select(MTSymbol).where(MTSymbol.account_id == account.id, MTSymbol.canonical_symbol == canonical))
            if not mapping or not mapping.broker_symbol:
                continue
            entry = float(o.get("entry") or 0)
            sl = float(o.get("sl") or o.get("stop_loss") or 0)
            tps = o.get("tp") or o.get("take_profit") or []
            if isinstance(tps, (int, float, str)): tps = [tps]
            tp = float(tps[0]) if tps else 0
            volume = float(o.get("volume") or account.lot or getattr(core, "MT5_LOT_SIZE", 0.01))
            if min(entry, sl, tp, volume) <= 0:
                continue
            fp = _fingerprint(o, account.id)
            exists = session.scalar(select(MTOrder).where(MTOrder.account_id == account.id, MTOrder.source_fingerprint == fp))
            if exists:
                continue
            session.add(MTOrder(
                account_id=account.id, source_fingerprint=fp, canonical_symbol=canonical,
                execution_symbol=mapping.broker_symbol, direction=direction, volume=volume,
                entry=entry, stop_loss=sl, take_profit=tp,
                source=str(o.get("source") or "Consensus"), signal_id=str(o.get("signal_id") or o.get("id") or ""),
                candle_time=str(o.get("candle_time") or ""),
            ))
            created += 1
    if created:
        session.commit()
    return created

@router.get("/ui")
async def ui():
    return FileResponse(__import__("os").path.join(str(core.BASE_DIR), "mt5_accounts.html"), media_type="text/html")

@router.post("/pair")
async def create_pair(body: PairRequest, authorization: str | None = Header(default=None), session=Depends(core.db)):
    user = _user(authorization, session)
    code = secrets.token_hex(4).upper()
    session.add(MTPairing(user_id=user.id, code_hash=_hash(code), expires_at=_utc() + timedelta(minutes=PAIR_TTL_MINUTES)))
    session.commit()
    return {"ok": True, "pairing_code": code, "expires_in": PAIR_TTL_MINUTES * 60, "label": body.label}

@router.get("/accounts")
async def accounts(authorization: str | None = Header(default=None), session=Depends(core.db)):
    user = _user(authorization, session)
    rows = list(session.scalars(select(MT5Account).where(MT5Account.user_id == user.id).order_by(MT5Account.id.desc())))
    return {"items": [_account_dict(x) for x in rows]}

@router.post("/accounts/{account_id}/auto-trade")
async def toggle(account_id: int, body: ToggleRequest, authorization: str | None = Header(default=None), session=Depends(core.db)):
    user = _user(authorization, session)
    a = session.scalar(select(MT5Account).where(MT5Account.id == account_id, MT5Account.user_id == user.id))
    if not a: raise HTTPException(404, "MT5 account not found")
    if body.enabled and not a.connected:
        raise HTTPException(409, "MT5 account is not connected")
    a.auto_trade_enabled = bool(body.enabled)
    session.commit()
    return {"ok": True, "account": _account_dict(a)}

@router.post("/accounts/{account_id}/lot")
async def set_account_lot(account_id: int, body: LotRequest, authorization: str | None = Header(default=None), session=Depends(core.db)):
    user = _user(authorization, session)
    a = session.scalar(select(MT5Account).where(MT5Account.id == account_id, MT5Account.user_id == user.id))
    if not a:
        raise HTTPException(404, "MT5 account not found")
    mapping = session.scalar(select(MTSymbol).where(MTSymbol.account_id == account_id, MTSymbol.canonical_symbol == "XAU/USD"))
    lot = float(body.lot)
    if mapping:
        minimum = float(mapping.volume_min or 0.01)
        maximum = float(mapping.volume_max or 100.0)
        step = float(mapping.volume_step or 0.01)
        if lot < minimum or lot > maximum:
            raise HTTPException(422, f"Lot {minimum:g} - {maximum:g} oralig'ida bo'lishi kerak")
        steps = round((lot - minimum) / step)
        normalized = minimum + steps * step
        if abs(normalized - lot) > max(1e-9, step * 1e-6):
            raise HTTPException(422, f"Lot step {step:g} bo'yicha tanlanishi kerak")
        lot = normalized
    a.lot = lot
    session.commit()
    return {"ok": True, "account": _account_dict(a)}

@router.delete("/accounts/{account_id}")
async def disconnect(account_id: int, authorization: str | None = Header(default=None), session=Depends(core.db)):
    user = _user(authorization, session)
    a = session.scalar(select(MT5Account).where(MT5Account.id == account_id, MT5Account.user_id == user.id))
    if not a: raise HTTPException(404, "MT5 account not found")
    a.connected = False
    a.auto_trade_enabled = False
    a.account_token_hash = None
    session.commit()
    return {"ok": True}

@router.post("/register")
async def register(body: RegisterRequest, session=Depends(core.db)):
    pairing = session.scalar(select(MTPairing).where(MTPairing.code_hash == _hash(body.pairing_code.upper()), MTPairing.used == False))
    if not pairing or (_as_utc(pairing.expires_at) or _utc()) < _utc():
        raise HTTPException(401, "Pairing code invalid or expired")
    pairing.used = True
    token = _account_token()
    a = MT5Account(
        user_id=pairing.user_id, label="MT5 " + (body.login or "Account"),
        broker=body.broker[:160], server=body.server[:200], login=body.login[:80],
        account_type=body.account_type.lower(), currency=body.currency[:20], leverage=int(body.leverage or 0),
        balance=float(body.balance or 0), equity=float(body.equity or 0), free_margin=float(body.free_margin or 0),
        margin=float(body.margin or 0), trade_allowed=bool(body.trade_allowed), connected=True,
        auto_trade_enabled=False, account_token_hash=_hash(token),
        token_expires_at=_utc() + timedelta(days=ACCOUNT_TOKEN_TTL_DAYS),
        last_seen_at=_utc(), terminal_build=body.terminal_build[:50], ea_version=body.ea_version[:50],
    )
    session.add(a)
    session.flush()
    for s in body.symbols:
        canonical = _canonical(str(s.get("canonical_symbol") or s.get("symbol") or ""))
        broker_symbol = str(s.get("broker_symbol") or s.get("symbol") or "")
        if not canonical or not broker_symbol: continue
        session.add(MTSymbol(
            account_id=a.id, canonical_symbol=canonical, broker_symbol=broker_symbol,
            digits=int(s.get("digits") or 2), point=float(s.get("point") or 0.01),
            volume_min=float(s.get("volume_min") or 0.01), volume_step=float(s.get("volume_step") or 0.01),
            volume_max=float(s.get("volume_max") or 100), trade_mode=str(s.get("trade_mode") or "unknown")[:50]
        ))
    session.commit()
    return {"ok": True, "account_id": a.id, "account_token": token, "auto_trade_enabled": False}

def _auth_account(token: str | None, session) -> MT5Account:
    if not token:
        raise HTTPException(401, "MT5 account token required")
    a = session.scalar(select(MT5Account).where(MT5Account.account_token_hash == _hash(token)))
    if not a:
        raise HTTPException(401, "Invalid MT5 account token")
    if a.token_expires_at and (_as_utc(a.token_expires_at) or _utc()) < _utc():
        raise HTTPException(401, "MT5 account token expired")
    return a

@router.post("/state")
async def state(body: MTState, authorization: str | None = Header(default=None), session=Depends(core.db)):
    token = authorization.split(" ", 1)[1].strip() if authorization and authorization.lower().startswith("bearer ") else authorization
    a = _auth_account(token, session)
    a.broker, a.server, a.login = body.broker[:160], body.server[:200], body.login[:80]
    a.account_type, a.currency = body.account_type.lower(), body.currency[:20]
    a.leverage, a.balance, a.equity = int(body.leverage or 0), float(body.balance or 0), float(body.equity or 0)
    a.free_margin, a.margin = float(body.free_margin or 0), float(body.margin or 0)
    a.trade_allowed, a.connected, a.last_seen_at = bool(body.trade_allowed), True, _utc()
    a.terminal_build, a.ea_version = body.terminal_build[:50], body.ea_version[:50]
    for s in body.symbols:
        canonical = _canonical(str(s.get("canonical_symbol") or s.get("symbol") or ""))
        broker_symbol = str(s.get("broker_symbol") or s.get("symbol") or "")
        if not canonical or not broker_symbol: continue
        row = session.scalar(select(MTSymbol).where(MTSymbol.account_id == a.id, MTSymbol.canonical_symbol == canonical))
        if not row:
            row = MTSymbol(account_id=a.id, canonical_symbol=canonical, broker_symbol=broker_symbol)
            session.add(row)
        row.broker_symbol = broker_symbol
        row.digits = int(s.get("digits") or row.digits or 2)
        row.point = float(s.get("point") or row.point or 0.01)
        row.volume_min = float(s.get("volume_min") or row.volume_min or 0.01)
        row.volume_step = float(s.get("volume_step") or row.volume_step or 0.01)
        row.volume_max = float(s.get("volume_max") or row.volume_max or 100)
        row.trade_mode = str(s.get("trade_mode") or row.trade_mode or "unknown")[:50]
    session.commit()
    return {"ok": True, "account": _account_dict(a)}

@router.get("/poll")
async def poll(authorization: str | None = Header(default=None), session=Depends(core.db)):
    token = authorization.split(" ", 1)[1].strip() if authorization and authorization.lower().startswith("bearer ") else authorization
    a = _auth_account(token, session)
    if not a.auto_trade_enabled or not a.trade_allowed:
        return {"orders": [], "reason": "autotrade_disabled_or_trading_not_allowed"}
    _sync_core_queue(session)
    now = _utc()
    rows = list(session.scalars(select(MTOrder).where(MTOrder.account_id == a.id, MTOrder.status == "PENDING").order_by(MTOrder.id.asc()).limit(10)))
    out = []
    for row in rows:
        if row.claim_until and (_as_utc(row.claim_until) or now) > now:
            continue
        row.claim_until = now + timedelta(seconds=CLAIM_SECONDS)
        out.append({
            "order_id": row.id, "canonical_symbol": row.canonical_symbol,
            "execution_symbol": row.execution_symbol, "direction": row.direction,
            "volume": row.volume, "entry": row.entry, "stop_loss": row.stop_loss,
            "take_profit": row.take_profit, "source": row.source, "signal_id": row.signal_id,
            "candle_time": row.candle_time,
        })
    session.commit()
    return {"orders": out, "account_id": a.id}

@router.post("/report")
async def report(body: ReportRequest, authorization: str | None = Header(default=None), session=Depends(core.db)):
    token = authorization.split(" ", 1)[1].strip() if authorization and authorization.lower().startswith("bearer ") else authorization
    a = _auth_account(token, session)
    row = session.scalar(select(MTOrder).where(MTOrder.id == body.order_id, MTOrder.account_id == a.id))
    if not row: raise HTTPException(404, "Order not found")
    allowed = {"SENT", "FILLED", "REJECTED", "FAILED", "CANCELLED"}
    row.status = body.status.upper() if body.status.upper() in allowed else "FAILED"
    row.broker_ticket = body.broker_ticket[:100]
    row.broker_retcode = body.broker_retcode[:100]
    row.broker_message = body.broker_message[:2000]
    row.claim_until = None
    session.commit()
    return {"ok": True}

@router.get("/health")
async def health(authorization: str | None = Header(default=None), session=Depends(core.db)):
    user = _user(authorization, session)
    rows = list(session.scalars(select(MT5Account).where(MT5Account.user_id == user.id)))
    return {"ok": True, "accounts": [_account_dict(a) for a in rows]}
