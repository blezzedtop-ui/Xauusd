from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import asyncio
import smtplib
import random
import string
from email.message import EmailMessage
import csv
import io
from urllib.parse import quote as urlquote
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi import WebSocket, WebSocketDisconnect
from book_openai_engine import book_signal, _atr as _atr_local
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

load_dotenv()

APP_TITLE = os.getenv("APP_TITLE", "Trading SaaS Analytics Platform")
MARKET_PROVIDER = os.getenv("MARKET_PROVIDER", "auto").lower()
REALMARKET_API_KEY = os.getenv("REALMARKET_API_KEY", "").strip()
REALMARKET_API_BASE = os.getenv("REALMARKET_API_BASE", "https://api.realmarketapi.com").strip().rstrip("/")
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "").strip()
TRADING_ECONOMICS_API_KEY = os.getenv("TRADING_ECONOMICS_API_KEY", "").strip()
CALENDAR_PROVIDER = os.getenv("CALENDAR_PROVIDER", "auto").strip().lower()
FOREX_FACTORY_CALENDAR_URL = os.getenv("FOREX_FACTORY_CALENDAR_URL", "https://www.forexfactory.com/calendar?export=csv&week=this").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5").strip() or "gpt-5"
ALLOW_DEMO = os.getenv("ALLOW_DEMO", "false").lower() == "true"
DEFAULT_SYMBOL = os.getenv("DEFAULT_SYMBOL", "XAU/USD").strip() or "XAU/USD"
DEFAULT_INTERVAL = os.getenv("DEFAULT_INTERVAL", "30min").strip() or "30min"
PIVOT_INTERVAL = os.getenv("PIVOT_INTERVAL", "1day").strip() or "1day"
PIVOT_NO_TRADE_PCT = float(os.getenv("PIVOT_NO_TRADE_PCT", "0.0010"))
SL_BUFFER_PCT = float(os.getenv("SL_BUFFER_PCT", "0.0015"))
NEWS_BLACKOUT_MINUTES = int(os.getenv("NEWS_BLACKOUT_MINUTES", "30"))
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER).strip()
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000").strip().rstrip("/")
REQUIRE_EMAIL_DELIVERY = os.getenv("REQUIRE_EMAIL_DELIVERY", "false").lower() == "true"
SMTP_USE_STARTTLS = os.getenv("SMTP_USE_STARTTLS", "true").lower() == "true"
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "false").lower() == "true"
AI_CACHE_TTL = int(os.getenv("AI_CACHE_TTL", "300"))
AI_RATE_LIMIT_RETRY_NEXT_CANDLE = True
# Book/OpenAI second-opinion cache: one OpenAI call per newly closed/current candle.
BOOK_OPENAI_CACHE_TTL = int(os.getenv("BOOK_OPENAI_CACHE_TTL", "300"))
BOOK_OPENAI_COOLDOWN = int(os.getenv("BOOK_OPENAI_COOLDOWN", "45"))
BOOK_OPENAI_CACHE: dict[str, tuple[float, int | None, dict[str, Any]]] = {}
BOOK_OPENAI_LOCKS: dict[str, asyncio.Lock] = {}
# Global OpenAI circuit breaker: prevents every endpoint/worker call from immediately
# retrying after a 429. It resets automatically after the cooldown.
OPENAI_GLOBAL_RATE_LIMIT_UNTIL = 0.0
OPENAI_GLOBAL_RATE_LIMIT_SECONDS = int(os.getenv("OPENAI_GLOBAL_RATE_LIMIT_SECONDS", "300"))
BOOK_OPENAI_LOCKS_GUARD = asyncio.Lock()
CANDLE_LIMIT = max(50, min(int(os.getenv("CANDLE_LIMIT", "220")), 500))
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "12"))
NODE_MARKET_URL = os.getenv("NODE_MARKET_URL", "http://127.0.0.1:3001").strip().rstrip("/")
TRADINGVIEW_SYMBOL = os.getenv("TRADINGVIEW_SYMBOL", "OANDA:XAUUSD").strip() or "OANDA:XAUUSD"
TRADINGVIEW_WS_URL = os.getenv("TRADINGVIEW_WS_URL", "wss://data.tradingview.com/socket.io/websocket").strip()
TRADINGVIEW_BARS = max(80, min(int(os.getenv("TRADINGVIEW_BARS", "260")), 500))
TRADINGVIEW_TIMEOUT = float(os.getenv("TRADINGVIEW_TIMEOUT", "10"))
TRADINGVIEW_CACHE_TTL = float(os.getenv("TRADINGVIEW_CACHE_TTL", "2.0"))
TV_CANDLE_CACHE: dict[tuple[str,str], tuple[float, list[dict[str,Any]]]] = {}
TV_CANDLE_LOCKS: dict[tuple[str,str], asyncio.Lock] = {}
TV_CANDLE_LOCKS_GUARD = asyncio.Lock()
NODE_QUOTE_TIMEOUT = float(os.getenv("NODE_QUOTE_TIMEOUT", "2.5"))
MARKET_TIMEZONE = os.getenv("MARKET_TIMEZONE", "UTC").strip() or "UTC"
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production").strip()
SESSION_HOURS = int(os.getenv("SESSION_HOURS", "168"))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./trading_saas.db").strip()

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # email = real recipient address; username = generated login.
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    subscription: Mapped["Subscription | None"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class SessionToken(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    plan: Mapped[str] = mapped_column(String(50), default="free")
    status: Mapped[str] = mapped_column(String(30), default="active")
    renews_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user: Mapped[User] = relationship(back_populates="subscription")


class SignalHistory(Base):
    __tablename__ = "signal_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(50), index=True)
    interval: Mapped[str] = mapped_column(String(20))
    direction: Mapped[str] = mapped_column(String(20))
    headline: Mapped[str] = mapped_column(String(255))
    price: Mapped[float] = mapped_column(Float)
    payload: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


Base.metadata.create_all(engine)

def ensure_schema() -> None:
    """Add the username column/index to databases created by previous versions."""
    try:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        columns = {c["name"] for c in inspector.get_columns("users")}
        with engine.begin() as conn:
            if "username" not in columns:
                conn.exec_driver_sql("ALTER TABLE users ADD COLUMN username VARCHAR(80)")
            conn.exec_driver_sql("UPDATE users SET username = email WHERE username IS NULL OR username = ''")
            conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_username ON users (username)")
    except Exception as exc:
        print(f"DB schema migration warning: {type(exc).__name__}: {exc}")


def ensure_admin_user() -> None:
    """Create/update the site owner's admin account from environment defaults."""
    admin_login = os.getenv("ADMIN_LOGIN", "Shohruh").strip() or "Shohruh"
    admin_password = os.getenv("ADMIN_PASSWORD", "Shox1337")
    with SessionLocal() as s:
        current = s.scalar(select(User).where(User.username == admin_login))
        if current is None:
            # Keep compatibility with old builds where the login was stored in email.
            current = s.scalar(select(User).where(User.email == admin_login))
        if current is None:
            current = s.scalar(select(User).where(User.email == "admin"))
        if current is None:
            current = User(email=admin_login.lower() + "@local.invalid", username=admin_login, password_hash=hash_password(admin_password))
            s.add(current)
        else:
            current.username = admin_login
            current.password_hash = hash_password(admin_password)
        if not current.subscription:
            current.subscription = Subscription(plan="admin", status="active", renews_at=None)
        else:
            current.subscription.plan = "admin"
            current.subscription.status = "active"
        s.commit()


def initialize_database() -> None:
    ensure_schema()
    ensure_admin_user()


app = FastAPI(title=APP_TITLE, version="19.0.0")
origins_raw = os.getenv("FRONTEND_ORIGINS", "*")
origins = [x.strip() for x in origins_raw.split(",") if x.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=origins != ["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)



BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Serve the complete frontend from the same FastAPI/Railway service.
# The previous build returned 404 for /app.js, /config.js and /assets/*,
# so the browser loaded the HTML but never executed the dashboard JavaScript.
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

@app.get("/app.js")
async def serve_app_js() -> FileResponse:
    return FileResponse(os.path.join(BASE_DIR, "app.js"), media_type="application/javascript")

@app.get("/config.js")
async def serve_config_js() -> FileResponse:
    return FileResponse(os.path.join(BASE_DIR, "config.js"), media_type="application/javascript")

@app.get("/manifest.webmanifest")
async def serve_manifest() -> FileResponse:
    return FileResponse(os.path.join(BASE_DIR, "manifest.webmanifest"), media_type="application/manifest+json")

TIMEFRAME_SECONDS = {
    "1min": 60,
    "5min": 300,
    "15min": 900,
    "30min": 1800,
    "1h": 3600,
    "4h": 14400,
    "1day": 86400,
}
VALID_INTERVALS = tuple(TIMEFRAME_SECONDS.keys())
AI_CACHE: dict[str, tuple[float, str | None, dict[str, Any]]] = {}
AI_LOCKS: dict[str, asyncio.Lock] = {}
AI_LOCKS_GUARD = asyncio.Lock()
MARKET_HISTORY_CACHE: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}
MARKET_HISTORY_CACHE_TTL = int(os.getenv("MARKET_HISTORY_CACHE_TTL", "5"))
LIVE_PRICE_CACHE: dict[str, tuple[float, float, str]] = {}
ADVANCED_SIGNAL_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
MTF_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
ADVANCED_CACHE_TTL = float(os.getenv("ADVANCED_CACHE_TTL", "5"))
MTF_CACHE_TTL = float(os.getenv("MTF_CACHE_TTL", "10"))
LIVE_PRICE_CACHE_TTL = float(os.getenv("LIVE_PRICE_CACHE_TTL", "1.5"))
AUTO_ENTRY_ENABLED = os.getenv("AUTO_ENTRY_ENABLED", "true").lower() == "true"
AUTO_ENTRY_THRESHOLD = float(os.getenv("AUTO_ENTRY_THRESHOLD", "85"))
AUTO_ENTRY_DUPLICATE_MINUTES = int(os.getenv("AUTO_ENTRY_DUPLICATE_MINUTES", "5"))


def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 180_000)
    return salt.hex() + ":" + digest.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split(":", 1)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 180_000)
        return secrets.compare_digest(digest.hex(), digest_hex)
    except ValueError:
        return False


initialize_database()

def token_hash(token: str) -> str:
    return hashlib.sha256((SECRET_KEY + token).encode()).hexdigest()


def create_session(user_id: int, session: Session) -> str:
    raw = secrets.token_urlsafe(48)
    item = SessionToken(
        user_id=user_id,
        token_hash=token_hash(raw),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS),
    )
    session.add(item)
    session.commit()
    return raw


def current_user(authorization: str | None, session: Session) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    raw = authorization.split(" ", 1)[1].strip()
    row = session.scalar(select(SessionToken).where(SessionToken.token_hash == token_hash(raw)))
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    expiry = row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at.tzinfo is None else row.expires_at
    if expiry < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    user = session.get(User, row.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


class AuthBody(BaseModel):
    username: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class RegisterBody(BaseModel):
    email: str = Field(min_length=5, max_length=255)


def valid_email(value: str) -> bool:
    return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]{2,}", value.strip()))


def generate_credentials() -> tuple[str, str]:
    login = "gold-" + secrets.token_hex(4).upper()
    password = secrets.token_urlsafe(9)
    return login, password

@app.post("/api/auth/login")
async def auth_login(body: AuthBody, session: Session = Depends(db)) -> dict[str, Any]:
    """Stable username/password login endpoint used by the dashboard."""
    identity = body.username.strip()
    user = session.scalar(select(User).where(User.username == identity))
    if user is None and valid_email(identity):
        user = session.scalar(select(User).where(User.email == identity.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Login yoki parol noto‘g‘ri")
    raw = create_session(user.id, session)
    plan = user.subscription.plan if user.subscription else "free"
    return {"token": raw, "user": {"id": user.id, "username": user.username, "email": user.email, "plan": plan}}


@app.post("/api/auth/register")
async def auth_register(body: RegisterBody, session: Session = Depends(db)) -> dict[str, Any]:
    """Create a user without requiring SMTP; credentials are returned once so mobile users can enter them."""
    email = body.email.strip().lower()
    if not valid_email(email):
        raise HTTPException(status_code=422, detail="To‘g‘ri email manzilini kiriting")
    if session.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Bu email allaqachon ro‘yxatdan o‘tgan")
    login, password = generate_credentials()
    while session.scalar(select(User).where(User.username == login)):
        login, password = generate_credentials()
    user = User(email=email, username=login, password_hash=hash_password(password))
    session.add(user)
    session.flush()
    user.subscription = Subscription(plan="free", status="active")
    session.commit()
    raw = create_session(user.id, session)
    email_ok, email_message = send_credentials_email(email, login, password)
    return {
        "token": raw,
        "user": {"id": user.id, "username": login, "email": email, "plan": "free"},
        "credentials": {"login": login, "password": password},
        "email_message": email_message if email_ok else "Email yuborilmadi, login/parol shu yerda ko‘rsatildi."
    }


@app.post("/api/auth/logout")
async def auth_logout(authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization.split(" ", 1)[1].strip()
        row = session.scalar(select(SessionToken).where(SessionToken.token_hash == token_hash(raw)))
        if row:
            session.delete(row)
            session.commit()
    return {"ok": True}


@app.get("/api/auth/me")
async def auth_me(authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    user = current_user(authorization, session)
    plan = user.subscription.plan if user.subscription else "free"
    return {"user": {"id": user.id, "username": user.username, "email": user.email, "plan": plan}}


def smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_PORT and SMTP_USER and SMTP_PASSWORD and (SMTP_FROM or SMTP_USER))


def smtp_diagnostic_message(exc: Exception) -> str:
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        code = getattr(exc, "smtp_code", None)
        if SMTP_HOST == "smtp.gmail.com":
            return (
                f"Gmail SMTP authentication xatosi ({code}). SMTP_USER to'liq Gmail manzili bo'lishi, "
                "2-Step Verification yoqilgan bo'lishi va SMTP_PASSWORD 16 belgili Google App Password bo'lishi kerak. "
                "Oddiy Gmail paroli ishlamaydi."
            )
        return f"SMTP authentication xatosi ({code}). SMTP_USER/SMTP_PASSWORDni tekshiring."
    return f"Email yuborishda SMTP xatosi: {type(exc).__name__}."


def send_credentials_email(recipient: str, login: str, password: str) -> tuple[bool, str]:
    """Send credentials via SMTP with robust Gmail/Outlook/Yandex support."""
    if not smtp_configured():
        return False, "SMTP sozlanmagan: .env faylida SMTP_USER, SMTP_PASSWORD va SMTP_FROM ni kiriting."
    sender = SMTP_FROM or SMTP_USER
    msg = EmailMessage()
    msg["Subject"] = "GOLD TRADING — Kirish ma'lumotlari"
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(
        "Assalomu alaykum!\n\n"
        "GOLD TRADING SaaS hisobingiz muvaffaqiyatli yaratildi.\n\n"
        f"Login: {login}\n"
        f"Parol: {password}\n\n"
        f"Kirish manzili: {APP_BASE_URL}\n\n"
        "Login va parolingizni boshqa odamlarga bermang."
    )
    clean_password = re.sub(r"\s+", "", SMTP_PASSWORD)
    try:
        use_ssl = SMTP_USE_SSL or SMTP_PORT == 465
        use_starttls = SMTP_USE_STARTTLS and not use_ssl and SMTP_PORT != 465
        if use_ssl:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=25) as server:
                server.ehlo()
                server.login(SMTP_USER, clean_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=25) as server:
                server.ehlo()
                if use_starttls:
                    server.starttls()
                    server.ehlo()
                server.login(SMTP_USER, clean_password)
                server.send_message(msg)
        return True, "Login va parol emailingizga yuborildi."
    except (smtplib.SMTPException, OSError) as exc:
        detail = smtp_diagnostic_message(exc)
        print(f"SMTP error ({SMTP_HOST}:{SMTP_PORT}) -> {recipient}: {type(exc).__name__}: {exc}")
        return False, detail


class MarketDataError(RuntimeError):
    pass


def clean_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace("-", "/")

def realmarket_symbol(symbol: str) -> str:
    return clean_symbol(symbol).replace("/", "")

REALMARKET_TIMEFRAMES = {"1min":"M1","5min":"M5","15min":"M15","1h":"H1","4h":"H4","1day":"D1"}

def realmarket_timeframe(interval: str) -> str:
    interval = validate_interval(interval)
    if interval not in REALMARKET_TIMEFRAMES:
        raise MarketDataError(f"RealMarketAPI does not publish {interval} in its documented timeframe set; use Twelve Data for this timeframe.")
    return REALMARKET_TIMEFRAMES[interval]

def live_provider() -> str | None:
    if MARKET_PROVIDER in ("realmarketapi", "realmarket") and REALMARKET_API_KEY:
        return "realmarketapi"
    if MARKET_PROVIDER == "twelvedata" and TWELVE_DATA_API_KEY:
        return "twelvedata"
    if MARKET_PROVIDER == "yahoo":
        return "yahoo"
    if MARKET_PROVIDER == "auto":
        if REALMARKET_API_KEY:
            return "realmarketapi"
        if TWELVE_DATA_API_KEY:
            return "twelvedata"
        # Cloud/no-key fallback: Yahoo Finance chart endpoint. This keeps the app
        # usable after deployment without requiring the user's PC or a market API key.
        return "yahoo"
    return None


def validate_interval(interval: str) -> str:
    value = interval.strip().lower()
    aliases = {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min", "1h": "1h", "4h": "4h", "1d": "1day", "d1": "1day"}
    value = aliases.get(value, value)
    if value not in VALID_INTERVALS:
        raise HTTPException(status_code=400, detail=f"Unsupported interval. Use: {', '.join(VALID_INTERVALS)}")
    return value


def to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise MarketDataError(f"Invalid numeric value: {value!r}") from exc


def sma(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    data = values[-period:]
    return sum(data) / len(data)


def rsi(candles: list[dict[str, Any]], period: int = 14) -> float:
    closes = [float(c["close"]) for c in candles]
    if len(closes) <= period:
        return 50.0
    gains, losses = [], []
    for i in range(-period, 0):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    avg_gain, avg_loss = mean(gains), mean(losses)
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr(candles: list[dict[str, Any]], period: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    values = []
    for i in range(max(1, len(candles) - period), len(candles)):
        c, prev = candles[i], candles[i - 1]["close"]
        values.append(max(c["high"] - c["low"], abs(c["high"] - prev), abs(c["low"] - prev)))
    return sum(values) / len(values) if values else 0.0


def calculate_pivot_levels(high: float, low: float, close: float, current: float) -> dict[str, Any]:
    pivot = (high + low + close) / 3.0
    return {
        "bias": "BULLISH" if current >= pivot else "BEARISH",
        "pivot": round(pivot, 2),
        "r1": round((2 * pivot) - low, 2),
        "r2": round(pivot + (high - low), 2),
        "r3": round(high + 2 * (pivot - low), 2),
        "s1": round((2 * pivot) - high, 2),
        "s2": round(pivot - (high - low), 2),
        "s3": round(low - 2 * (high - pivot), 2),
        "reference_high": round(high, 2),
        "reference_low": round(low, 2),
        "reference_close": round(close, 2),
    }


def build_key_level_signal(candles: list[dict[str, Any]], levels: dict[str, Any], news_blocked: bool = False) -> dict[str, Any]:
    current = candles[-1]
    prev = candles[-2] if len(candles) > 1 else current
    pivot = levels["pivot"]
    bias = levels["bias"]
    average_range = atr(candles)
    pivot_buffer = max(abs(pivot) * PIVOT_NO_TRADE_PCT, average_range * 0.15)
    near_pivot = abs(current["close"] - pivot) <= pivot_buffer
    result = {
        "signal": "WAIT", "setup": "NO_TRADE", "entry": None, "stop_loss": None,
        "take_profit": [], "reason": "No confirmed Pivot retest/breakout setup.",
        "pivot_filter": bias, "pivot_zone": round(pivot_buffer, 2),
    }
    if news_blocked:
        result.update(setup="NEWS_BLACKOUT", reason="High-impact news window is active; new entries are blocked.")
        return result
    if near_pivot:
        result.update(setup="PIVOT_NO_TRADE", reason="Price is inside the Pivot no-trade zone.")
        return result

    bearish_retest = prev["close"] < pivot and current["high"] >= pivot and current["close"] < pivot and current["close"] < current["open"]
    bullish_retest = prev["close"] > pivot and current["low"] <= pivot and current["close"] > pivot and current["close"] > current["open"]
    bearish_breakout = current["close"] < levels["s1"] and prev["close"] >= levels["s1"]
    bullish_breakout = current["close"] > levels["r1"] and prev["close"] <= levels["r1"]

    if bias == "BEARISH" and (bearish_retest or bearish_breakout):
        sl = max(current["high"], pivot) * (1 + SL_BUFFER_PCT)
        result.update(signal="SELL", setup="PIVOT_RETEST" if bearish_retest else "S1_BREAKOUT", entry=round(current["close"], 2), stop_loss=round(sl, 2), take_profit=[levels["s1"], levels["s2"]], reason="Bearish Pivot filter confirmed with rejection/breakdown.")
    elif bias == "BULLISH" and (bullish_retest or bullish_breakout):
        sl = min(current["low"], pivot) * (1 - SL_BUFFER_PCT)
        result.update(signal="BUY", setup="PIVOT_RETEST" if bullish_retest else "R1_BREAKOUT", entry=round(current["close"], 2), stop_loss=round(sl, 2), take_profit=[levels["r1"], levels["r2"]], reason="Bullish Pivot filter confirmed with rejection/breakout.")
    elif bias == "BEARISH" and current["close"] <= levels["s2"]:
        result.update(setup="TARGET_REACHED", reason="S2/S3 target zone reached; fresh SELL entries are blocked.")
    elif bias == "BULLISH" and current["close"] >= levels["r2"]:
        result.update(setup="TARGET_REACHED", reason="R2/R3 target zone reached; fresh BUY entries are blocked.")
    return result


async def td_get(endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
    if not TWELVE_DATA_API_KEY:
        raise MarketDataError("TWELVE_DATA_API_KEY is not configured")
    request_params = dict(params)
    request_params["apikey"] = TWELVE_DATA_API_KEY
    url = f"https://api.twelvedata.com/{endpoint.lstrip('/')}"
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(url, params=request_params)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        raise MarketDataError(f"Twelve Data request failed: {exc}") from exc
    if isinstance(data, dict) and data.get("status") == "error":
        raise MarketDataError(data.get("message", "Twelve Data returned an error"))
    return data


async def fetch_twelvedata_candles(symbol: str, interval: str, limit: int) -> list[dict[str, Any]]:
    data = await td_get("time_series", {"symbol": symbol, "interval": validate_interval(interval), "outputsize": limit, "format": "JSON", "timezone": MARKET_TIMEZONE})
    candles: list[dict[str, Any]] = []
    for row in reversed(data.get("values") or []):
        try:
            ts = datetime.fromisoformat(str(row["datetime"]).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            candles.append({"time": int(ts.timestamp()), "open": to_float(row["open"]), "high": to_float(row["high"]), "low": to_float(row["low"]), "close": to_float(row["close"])})
        except (KeyError, MarketDataError, ValueError):
            continue
    if not candles:
        raise MarketDataError("No candle data returned")
    return candles


def history_required_points(interval: str, days: int = 31) -> int:
    seconds = TIMEFRAME_SECONDS[validate_interval(interval)]
    return int((days * 86400) / seconds) + 5


async def fetch_twelvedata_month_candles(symbol: str, interval: str, days: int = 31) -> list[dict[str, Any]]:
    """Fetch at least one month of candles using bounded 5,000-point requests.

    Twelve Data documents a maximum of 5,000 points per request; longer windows are
    therefore fetched in chronological chunks and merged locally.
    """
    interval = validate_interval(interval)
    key = (clean_symbol(symbol), interval)
    now_mono = asyncio.get_running_loop().time()
    cached = MARKET_HISTORY_CACHE.get(key)
    if cached and now_mono - cached[0] < MARKET_HISTORY_CACHE_TTL:
        return cached[1]

    total_points = history_required_points(interval, days)
    step_seconds = TIMEFRAME_SECONDS[interval]
    max_points = 5000
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days)
    merged: dict[int, dict[str, Any]] = {}

    cursor_end = end_dt
    remaining = total_points
    while remaining > 0:
        points = min(max_points, remaining)
        chunk_start = max(start_dt, cursor_end - timedelta(seconds=step_seconds * points))
        params = {
            "symbol": clean_symbol(symbol),
            "interval": interval,
            "start_date": chunk_start.strftime("%Y-%m-%d %H:%M:%S"),
            "end_date": cursor_end.strftime("%Y-%m-%d %H:%M:%S"),
            "format": "JSON",
            "timezone": MARKET_TIMEZONE,
        }
        data = await td_get("time_series", params)
        values = data.get("values") or []
        for row in values:
            try:
                ts = datetime.fromisoformat(str(row["datetime"]).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                item = {"time": int(ts.timestamp()), "open": to_float(row["open"]), "high": to_float(row["high"]), "low": to_float(row["low"]), "close": to_float(row["close"])}
                merged[item["time"]] = item
            except (KeyError, MarketDataError, ValueError):
                continue
        remaining -= points
        if not values or chunk_start <= start_dt:
            break
        cursor_end = chunk_start - timedelta(seconds=1)

    candles = [merged[k] for k in sorted(merged)]
    if not candles:
        raise MarketDataError("No historical candle data returned")
    MARKET_HISTORY_CACHE[key] = (now_mono, candles)
    return candles


async def rm_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """RealMarketAPI REST helper aligned with the current public API.

    Current docs expose /api/v1/price, /api/v1/candle and /api/v1/history and
    authenticate with apiKey in the query string. We keep the base URL configurable
    but normalize these three paths automatically so a default base URL cannot produce
    a false 404 from /price or /history.
    """
    if not REALMARKET_API_KEY:
        raise MarketDataError("REALMARKET_API_KEY is not configured")
    params = dict(params or {})
    params["apiKey"] = REALMARKET_API_KEY
    normalized = path.lstrip('/')
    if normalized in {"price", "candle", "history", "symbol", "symbols", "health"}:
        endpoint = f"api/v1/{normalized}"
    elif normalized.startswith("api/v1/"):
        endpoint = normalized
    else:
        endpoint = normalized
    url = f"{REALMARKET_API_BASE}/{endpoint}"
    headers = {"Accept": "application/json", "User-Agent": "GOLD-Trading-SaaS/36"}
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            r = await client.get(url, params=params, headers=headers)
            text = r.text[:1200]
            if r.status_code >= 400:
                try:
                    body = r.json()
                    detail = body.get("error") or body.get("message") or body.get("Message") or text
                except Exception:
                    detail = text
                raise MarketDataError(f"RealMarketAPI HTTP {r.status_code} at /{endpoint}: {detail[:800]}")
            try:
                data = r.json()
            except ValueError as exc:
                raise MarketDataError(f"RealMarketAPI returned non-JSON from /{endpoint}: {text[:500]}") from exc
    except MarketDataError:
        raise
    except httpx.HTTPError as exc:
        raise MarketDataError(f"RealMarketAPI request failed: {exc}") from exc
    if isinstance(data, dict) and str(data.get("status", "")).lower() == "error":
        raise MarketDataError(data.get("message") or data.get("error") or "RealMarketAPI returned an error")
    return data


def _rm_rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list): return [x for x in data if isinstance(x,dict)]
    if not isinstance(data,dict): return []
    for key in ("data","Data","items","Items","values","Values","candles","Candles","results","Results"):
        v=data.get(key)
        if isinstance(v,list): return [x for x in v if isinstance(x,dict)]
    for key in ("result","Result","payload","Payload"):
        v=data.get(key)
        if isinstance(v,dict):
            rows=_rm_rows(v)
            if rows: return rows
    return []

def _rm_candle(row: dict[str, Any]) -> dict[str, Any]:
    t=row.get("time") or row.get("Time") or row.get("openTime") or row.get("OpenTime") or row.get("timestamp") or row.get("Timestamp")
    if isinstance(t,(int,float)): ts=int(float(t))
    else:
        dt=datetime.fromisoformat(str(t).replace("Z","+00:00"))
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        ts=int(dt.timestamp())
    def pick(a,b): return row[a] if row.get(a) is not None else row.get(b)
    return {"time":ts,"open":to_float(pick("open","OpenPrice")),"high":to_float(pick("high","HighPrice")),"low":to_float(pick("low","LowPrice")),"close":to_float(pick("close","ClosePrice"))}

async def fetch_realmarket_candles(symbol: str, interval: str, limit: int) -> list[dict[str, Any]]:
    interval = validate_interval(interval)
    if interval == "30min":
        # RealMarketAPI documents M30 as unsupported. Build M30 from M15 candles.
        base = await fetch_realmarket_candles(symbol, "15min", min(limit * 2 + 20, 400))
        return aggregate_candles(base, 30 * 60)[-limit:]
    # /api/v1/candle returns recent bars, newest first; it does not require page args.
    data = await rm_get("candle", {
        "symbolCode": realmarket_symbol(symbol),
        "timeFrame": realmarket_timeframe(interval),
    })
    candles: list[dict[str, Any]] = []
    for row in _rm_rows(data):
        try: candles.append(_rm_candle(row))
        except Exception: continue
    candles.sort(key=lambda x: x["time"])
    if not candles:
        # Fallback to /api/v1/history only where the provider documents historical
        # support (currently H1 history). For other intervals we retain the recent
        # candle response instead of turning a valid recent-data request into a 404.
        if interval != "1h":
            raise MarketDataError("RealMarketAPI history is documented for H1; use /candle for this timeframe")
        end_dt = datetime.now(timezone.utc); start_dt = end_dt - timedelta(days=7)
        data = await rm_get("history", {
            "symbolCode": realmarket_symbol(symbol),
            "startTime": start_dt.isoformat().replace("+00:00", "Z"),
            "endTime": end_dt.isoformat().replace("+00:00", "Z"),
            "pageNumber": 1, "pageSize": min(max(int(limit), 10), 200),
        })
        for row in _rm_rows(data):
            try: candles.append(_rm_candle(row))
            except Exception: continue
        candles.sort(key=lambda x: x["time"])
    if not candles:
        raise MarketDataError("RealMarketAPI returned no candles for this symbol/timeframe")
    return candles[-min(limit, len(candles)):]

async def fetch_realmarket_month_candles(symbol: str, interval: str, days: int = 31) -> list[dict[str, Any]]:
    interval = validate_interval(interval)
    if interval == "30min":
        base = await fetch_realmarket_month_candles(symbol, "15min", days)
        return aggregate_candles(base, 30 * 60)
    # /api/v1/candle returns recent bars. Request enough bars for the local
    # indicator/signal engine instead of the previous 10-bar shortcut.
    # 30min is locally aggregated from M15.
    if interval != "1h":
        return await fetch_realmarket_candles(symbol, interval, 260)
    cache_key = ("realmarket-history", clean_symbol(symbol), interval, days)
    now = asyncio.get_running_loop().time()
    cached = MARKET_HISTORY_CACHE.get(cache_key)
    if cached and now - cached[0] < MARKET_HISTORY_CACHE_TTL:
        return cached[1]
    end = datetime.now(timezone.utc); start = end - timedelta(days=days)
    merged: dict[int, dict[str, Any]] = {}
    page = 1
    while page <= 100:
        data = await rm_get("history", {
            "symbolCode": realmarket_symbol(symbol),
            "timeFrame": realmarket_timeframe(interval),
            "startTime": start.isoformat().replace("+00:00", "Z"),
            "endTime": end.isoformat().replace("+00:00", "Z"),
            "pageNumber": page,
            "pageSize": 200,
        })
        rows = _rm_rows(data)
        if not rows: break
        for row in rows:
            try:
                c = _rm_candle(row); merged[c["time"]] = c
            except Exception: continue
        total = data.get("totalPages") if isinstance(data, dict) else None
        if total is None: total = data.get("TotalPages") if isinstance(data, dict) else None
        if total is not None:
            try:
                if page >= int(total): break
            except Exception: pass
        if len(rows) < 200: break
        page += 1
    candles = [merged[k] for k in sorted(merged)]
    if not candles:
        raise MarketDataError("RealMarketAPI historical data unavailable for this symbol/timeframe/plan")
    MARKET_HISTORY_CACHE[cache_key] = (now, candles)
    return candles

def aggregate_candles(candles: list[dict[str, Any]], seconds: int) -> list[dict[str, Any]]:
    if not candles: return []
    buckets: dict[int, dict[str, Any]] = {}
    for c in candles:
        bucket = int(c["time"]) // seconds * seconds
        if bucket not in buckets:
            buckets[bucket] = {"time": bucket, "open": c["open"], "high": c["high"], "low": c["low"], "close": c["close"]}
        else:
            x = buckets[bucket]; x["high"] = max(x["high"], c["high"]); x["low"] = min(x["low"], c["low"]); x["close"] = c["close"]
    return [buckets[k] for k in sorted(buckets)]


YAHOO_SYMBOLS = {"XAU/USD": "GC=F", "XAUUSD": "GC=F"}
YAHOO_FALLBACK_SYMBOLS = {"XAU/USD": "GC=F", "XAUUSD": "GC=F"}
YAHOO_INTERVALS = {"1min":"1m","5min":"5m","15min":"15m","30min":"30m","1h":"1h","1day":"1d"}
YAHOO_RANGES = {"1min":"7d","5min":"60d","15min":"60d","30min":"60d","1h":"730d","1day":"10y"}

async def fetch_yahoo_candles(symbol: str, interval: str, limit: int = 500) -> list[dict[str, Any]]:
    """Public Yahoo Finance chart fallback used when no paid market API key is configured."""
    interval = validate_interval(interval)
    base_symbol = clean_symbol(symbol)
    symbols_to_try = [YAHOO_SYMBOLS.get(base_symbol, base_symbol.replace("/", "") + "=X")]
    if base_symbol in YAHOO_FALLBACK_SYMBOLS:
        symbols_to_try.append(YAHOO_FALLBACK_SYMBOLS[base_symbol])
    source_interval = interval
    if interval == "4h":
        source_interval = "1h"
    if source_interval not in YAHOO_INTERVALS:
        raise MarketDataError(f"Yahoo fallback does not support {interval}")
    params = {"interval": YAHOO_INTERVALS[source_interval], "range": YAHOO_RANGES[source_interval], "events":"history", "includePrePost":"true"}
    last_error = None
    result = None
    yahoo_symbol = symbols_to_try[0]
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers={"User-Agent":"Mozilla/5.0"}) as client:
            for candidate in symbols_to_try:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urlquote(candidate, safe='')}"
                r = await client.get(url, params=params)
                if r.status_code >= 400:
                    last_error = f"Yahoo Finance HTTP {r.status_code} for {candidate}"
                    continue
                payload = r.json()
                result = ((payload.get("chart") or {}).get("result") or [None])[0]
                if result:
                    yahoo_symbol = candidate
                    break
                last_error = f"Yahoo Finance returned no chart data for {candidate}"
    except Exception as exc:
        raise MarketDataError(f"Yahoo Finance request failed: {type(exc).__name__}: {exc}") from exc
    if not result:
        raise MarketDataError(last_error or "Yahoo Finance returned no chart data")
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [None])[0] or {}
    rows=[]
    for i, ts in enumerate(timestamps):
        try:
            o,h,l,c = quote["open"][i], quote["high"][i], quote["low"][i], quote["close"][i]
            if None in (o,h,l,c):
                continue
            rows.append({"time":int(ts),"open":float(o),"high":float(h),"low":float(l),"close":float(c)})
        except (IndexError, TypeError, ValueError, KeyError):
            continue
    if interval == "4h":
        rows = aggregate_candles(rows, 4 * 3600)
    if not rows:
        raise MarketDataError("Yahoo Finance returned no usable candles")
    return rows[-limit:]

async def fetch_yahoo_price(symbol: str) -> float:
    # Yahoo often does not provide 1-minute futures candles reliably.
    # Use a short 5-minute chart and its latest usable close instead.
    rows = await fetch_yahoo_candles(symbol, "5min", 2)
    if not rows:
        raise MarketDataError("Yahoo Finance returned no price")
    return float(rows[-1]["close"])

async def get_chart_history(symbol: str, interval: str, days: int = 31) -> tuple[list[dict[str, Any]], str, str | None]:
    data=await fetch_tradingview_candles(symbol,interval,min(CANDLE_LIMIT,TRADINGVIEW_BARS))
    return data,"tradingview",f"TradingView {TRADINGVIEW_SYMBOL} chart series"


def _tv_session(prefix: str) -> str:
    return prefix + "_" + "".join(random.choice(string.ascii_lowercase) for _ in range(12))

def _tv_frame(method: str, params: list[Any]) -> str:
    payload=json.dumps({"m":method,"p":params},separators=(",",":"))
    return f"~m~{len(payload.encode('utf-8'))}~m~{payload}"

def _tv_interval(interval: str) -> str:
    return {"1min":"1","5min":"5","15min":"15","30min":"30","1h":"60","4h":"240","1day":"1D"}[validate_interval(interval)]

def _tv_parse_frames(raw: str) -> list[dict[str,Any]]:
    out=[]; pos=0
    while pos < len(raw):
        if raw.startswith("~m~",pos):
            end=raw.find("~m~",pos+3)
            if end<0: break
            try:n=int(raw[pos+3:end])
            except ValueError: break
            st=end+3; payload=raw[st:st+n]; pos=st+n
            try: out.append(json.loads(payload))
            except Exception: pass
        else: pos+=1
    return out

async def _fetch_tradingview_candles_once(symbol: str, interval: str, limit: int = TRADINGVIEW_BARS) -> list[dict[str,Any]]:
    try: import websockets
    except Exception as exc: raise MarketDataError(f"TradingView WebSocket dependency unavailable: {exc}")
    tf=_tv_interval(interval); cs=_tv_session("cs"); qs=_tv_session("qs"); bars=[]
    try:
        async with websockets.connect(TRADINGVIEW_WS_URL, additional_headers={"Origin":"https://www.tradingview.com","User-Agent":"Mozilla/5.0"}, open_timeout=TRADINGVIEW_TIMEOUT, close_timeout=2, ping_interval=20, ping_timeout=20, max_size=8*1024*1024) as ws:
            async def send(m,p): await ws.send(_tv_frame(m,p))
            await send("set_auth_token",["unauthorized_user_token"])
            await send("chart_create_session",[cs,""])
            await send("quote_create_session",[qs])
            await send("quote_set_fields",[qs,"lp","ch","chp"])
            await send("quote_add_symbols",[qs,TRADINGVIEW_SYMBOL])
            resolve=json.dumps({"symbol":TRADINGVIEW_SYMBOL,"adjustment":"splits","session":"regular"},separators=(",",":"))
            await send("resolve_symbol",[cs,"sds_sym_1","="+resolve])
            await send("create_series",[cs,"sds_1","s1","sds_sym_1",tf,int(limit),""])
            deadline=asyncio.get_running_loop().time()+TRADINGVIEW_TIMEOUT
            while asyncio.get_running_loop().time()<deadline:
                try: raw=await asyncio.wait_for(ws.recv(),timeout=2.5)
                except asyncio.TimeoutError: continue
                if isinstance(raw,bytes): raw=raw.decode("utf-8","ignore")
                for hb in re.findall(r"~m~\d+~m~~h~([^~]+)",raw):
                    packet=f"~m~~h~{hb}"; await ws.send(f"~m~{len(packet)}~m~{packet}")
                for msg in _tv_parse_frames(raw):
                    m=msg.get("m"); pp=msg.get("p") or []
                    if m in {"critical_error","series_error","symbol_error"}: raise MarketDataError(f"TradingView {m}: {pp}")
                    if m!="timescale_update": continue
                    node=pp[1] if len(pp)>1 and isinstance(pp[1],dict) else {}
                    rawbars=(node.get("sds_1") or {}).get("s") or []
                    parsed=[]
                    for item in rawbars:
                        v=item.get("v") if isinstance(item,dict) else None
                        if not isinstance(v,list) or len(v)<5: continue
                        try:
                            t,o,h,l,c=map(float,v[:5])
                            if all(math.isfinite(x) for x in (t,o,h,l,c)): parsed.append({"time":int(t),"open":o,"high":h,"low":l,"close":c})
                        except Exception: pass
                    if parsed:
                        bars=sorted({b["time"]:b for b in parsed}.values(),key=lambda x:x["time"])
                        if len(bars)>=min(20,limit): return bars[-limit:]
            if bars:return bars[-limit:]
            raise MarketDataError("TradingView returned no OHLC bars")
    except MarketDataError: raise
    except Exception as exc: raise MarketDataError(f"TradingView WebSocket unavailable: {type(exc).__name__}: {exc}")


async def fetch_tradingview_candles(symbol: str, interval: str, limit: int = TRADINGVIEW_BARS) -> list[dict[str,Any]]:
    """Shared TradingView/OANDA cache. One request/connection per symbol+TF at a time.

    The dashboard has several panels that ask for the same candles simultaneously.
    Opening a fresh TradingView websocket for every panel/quote caused intermittent
    reconnects and empty data. This single-flight cache makes every module consume
    the exact same TradingView series. No market-data provider fallback is used.
    """
    symbol = clean_symbol(symbol)
    interval = validate_interval(interval)
    key = (symbol, interval)
    now = asyncio.get_running_loop().time()
    cached = TV_CANDLE_CACHE.get(key)
    if cached and now - cached[0] < TRADINGVIEW_CACHE_TTL and cached[1]:
        return cached[1][-limit:]
    async with TV_CANDLE_LOCKS_GUARD:
        lock = TV_CANDLE_LOCKS.setdefault(key, asyncio.Lock())
    async with lock:
        now = asyncio.get_running_loop().time()
        cached = TV_CANDLE_CACHE.get(key)
        if cached and now - cached[0] < TRADINGVIEW_CACHE_TTL and cached[1]:
            return cached[1][-limit:]
        bars = await _fetch_tradingview_candles_once(symbol, interval, max(limit, 80))
        if not bars:
            raise MarketDataError("TradingView returned no OHLC bars")
        bars = sorted({int(b["time"]): b for b in bars}.values(), key=lambda x: x["time"])
        TV_CANDLE_CACHE[key] = (asyncio.get_running_loop().time(), bars[-TRADINGVIEW_BARS:])
        return TV_CANDLE_CACHE[key][1][-limit:]


async def fetch_tradingview_price(symbol: str) -> float:
    """Return the TradingView/OANDA XAUUSD quote used by the embedded chart.

    OANDA:XAUUSD is a CFD/metal symbol, so try TradingView's CFD scanner first.
    The forex scanner is retained only as a compatibility fallback.  We NEVER
    fall back to RealMarketAPI here: a different provider would create a visible
    price mismatch between the dashboard and the TradingView chart.
    """
    tv_symbol = os.getenv("TRADINGVIEW_SYMBOL", "OANDA:XAUUSD").strip() or "OANDA:XAUUSD"
    payload = {
        "filter": [],
        "options": {"lang": "en"},
        "symbols": {"query": {"types": []}, "tickers": [tv_symbol]},
        "columns": ["close"],
        "range": [0, 1],
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; GOLD-Trading-SaaS/1.0)",
    }
    errors = []
    async with httpx.AsyncClient(timeout=min(REQUEST_TIMEOUT, 6.0)) as client:
        for market in ("cfd", "forex"):
            try:
                r = await client.post(f"https://scanner.tradingview.com/{market}/scan", json=payload, headers=headers)
                if r.status_code >= 400:
                    errors.append(f"{market} HTTP {r.status_code}")
                    continue
                data = r.json()
                rows = data.get("data") if isinstance(data, dict) else None
                if not rows:
                    errors.append(f"{market}: no rows")
                    continue
                values = rows[0].get("d") if isinstance(rows[0], dict) else None
                if isinstance(values, list) and values and values[0] is not None:
                    return to_float(values[0])
                errors.append(f"{market}: no close")
            except Exception as exc:
                errors.append(f"{market}: {type(exc).__name__}: {exc}")
    raise MarketDataError("TradingView OANDA:XAUUSD quote unavailable. " + " | ".join(errors))


async def fetch_realmarket_price(symbol: str, interval: str = DEFAULT_INTERVAL) -> float:
    # Use the SAME timeframe that the chart/analysis selected. Hard-coding M1
    # can return HTTP 400 on plans that do not expose M1, even when M5/M15/H1
    # candles work correctly. M30 is locally built from the provider M15 feed.
    interval = validate_interval(interval)
    source_interval = "15min" if interval == "30min" else interval
    data = await rm_get("price", {
        "symbolCode": realmarket_symbol(symbol),
        "timeFrame": realmarket_timeframe(source_interval),
    })
    if isinstance(data, dict):
        candidates = [data.get(k) for k in ("price","Price","closePrice","ClosePrice","Close","last","Last","Bid","bid")]
        for value in candidates:
            if value is not None: return to_float(value)
        nested=data.get("data") or data.get("Data")
        if isinstance(nested, dict):
            for key in ("price","Price","closePrice","ClosePrice","Close","last","Last","Bid","bid"):
                if nested.get(key) is not None: return to_float(nested[key])
    raise MarketDataError(f"RealMarketAPI /price returned no usable price: {str(data)[:500]}")


async def fetch_twelvedata_price(symbol: str) -> float:
    return to_float((await td_get("price", {"symbol": symbol})).get("price"))


def demo_candles() -> list[dict[str, Any]]:
    now = int(datetime.now(timezone.utc).timestamp())
    base = 4440.0
    out = []
    for i in range(220):
        t = now - (220 - i) * 1800
        drift = math.sin(i / 7) * 35 + i * 0.12
        o = base + drift
        h = o + 12 + abs(math.sin(i)) * 5
        l = o - 11 - abs(math.cos(i * 0.8)) * 4
        c = o + math.sin(i * 1.5) * 9
        out.append({"time": t, "open": round(o, 2), "high": round(max(o, h, c), 2), "low": round(min(o, l, c), 2), "close": round(c, 2)})
    return out


async def fetch_live_price_any(symbol: str, interval: str = DEFAULT_INTERVAL) -> tuple[float, str]:
    """Return the latest close from the exact TradingView chart series used by analysis."""
    key=clean_symbol(symbol); now=asyncio.get_running_loop().time()
    cached=LIVE_PRICE_CACHE.get(key)
    if cached and now-cached[0]<1.0:return cached[1],cached[2]
    bars=await fetch_tradingview_candles(symbol,interval,2)
    if not bars: raise MarketDataError("TradingView returned no live candle")
    price=float(bars[-1]["close"]); source=f"TradingView {TRADINGVIEW_SYMBOL} chart series"
    LIVE_PRICE_CACHE[key]=(now,price,source); return price,source

def merge_live_price_into_candles(candles: list[dict[str, Any]], interval: str, price: float) -> list[dict[str, Any]]:
    """Make the analysis candle represent the current live quote.

    TradingView is an embedded iframe, so its internal ticks cannot be read by the
    surrounding page. We therefore use the same configured live market providers
    for every analysis module and update the currently forming backend candle with
    the freshest quote.
    """
    if not candles:
        return candles
    seconds = TIMEFRAME_SECONDS[validate_interval(interval)]
    now_ts = int(datetime.now(timezone.utc).timestamp())
    bucket = (now_ts // seconds) * seconds
    out = [dict(c) for c in candles]
    last = out[-1]
    if int(last.get("time", 0)) == bucket:
        last["high"] = max(float(last["high"]), price)
        last["low"] = min(float(last["low"]), price)
        last["close"] = price
    elif int(last.get("time", 0)) < bucket:
        out.append({"time": bucket, "open": price, "high": price, "low": price, "close": price})
    else:
        last["close"] = price
    return out[-max(2, min(len(out), 500)):]


async def get_candles(symbol: str, interval: str, limit: int) -> tuple[list[dict[str, Any]], str, str | None]:
    interval = validate_interval(interval)
    data, _, _ = await get_chart_history(symbol, interval, max(31, min(limit, 260)))
    return data[-limit:], "tradingview", f"TradingView {TRADINGVIEW_SYMBOL} chart series"


async def get_pivot_reference(symbol: str) -> tuple[dict[str, float], str | None]:
    data=await fetch_tradingview_candles(symbol,"1day",5)
    if not data: raise MarketDataError("TradingView daily candles unavailable for pivot")
    base=data[-2] if len(data)>=2 else data[-1]
    return {"high":float(base["high"]),"low":float(base["low"]),"close":float(base["close"])},None

def timeframe_trend(candles: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [float(c["close"]) for c in candles]
    current = closes[-1]
    fast = sma(closes, min(10, len(closes)))
    slow = sma(closes, min(30, len(closes)))
    r = rsi(candles)
    if current > fast > slow and r >= 52:
        direction = "BULLISH"
    elif current < fast < slow and r <= 48:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"
    return {"trend": direction, "price": round(current, 4), "rsi": round(r, 2), "ema_fast_proxy": round(fast, 4), "ema_slow_proxy": round(slow, 4)}


async def multi_timeframe(symbol: str) -> dict[str, Any]:
    key=clean_symbol(symbol)
    now=asyncio.get_running_loop().time()
    cached=MTF_CACHE.get(key)
    if cached and now-cached[0] < MTF_CACHE_TTL:
        return cached[1]
    intervals=("1min","5min","15min","30min","1h","4h","1day")
    out={}; errors={}
    # One shared TV cache per timeframe; process sequentially to avoid opening 7 TV sockets at once.
    for tf in intervals:
        try:
            candles_data,mode,warning=await get_candles(key,tf,80)
            if len(candles_data)<2: raise MarketDataError("Not enough TradingView candles")
            out[tf]={**timeframe_trend(candles_data),"mode":mode,"warning":warning}
        except Exception as exc:
            errors[tf]=f"{type(exc).__name__}: {exc}"
    dirs=[x["trend"] for x in out.values() if x.get("trend")]
    score=dirs.count("BULLISH")-dirs.count("BEARISH")
    result={"timeframes":out,"overall":"BULLISH" if score>=2 else "BEARISH" if score<=-2 else "MIXED","bullish_count":dirs.count("BULLISH"),"bearish_count":dirs.count("BEARISH"),"available_count":len(out),"errors":errors,"mode":"tradingview"}
    MTF_CACHE[key]=(now,result)
    return result


def session_state(name: str, zone: str, now_utc: datetime) -> dict[str, Any]:
    local = now_utc.astimezone(ZoneInfo(zone))
    weekday = local.weekday() < 5
    if name == "Sydney":
        opened, closed = 8, 17
    elif name == "Tokyo":
        opened, closed = 9, 18
    elif name == "London":
        opened, closed = 8, 17
    else:
        opened, closed = 8, 17
    is_open = weekday and opened <= local.hour < closed
    return {"name": name, "timezone": zone, "open": is_open, "local_time": local.strftime("%H:%M:%S"), "hours": f"{opened:02d}:00–{closed:02d}:00"}


async def market_sessions() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {"now_utc": now.isoformat(), "sessions": [session_state("Sydney", "Australia/Sydney", now), session_state("Tokyo", "Asia/Tokyo", now), session_state("London", "Europe/London", now), session_state("New York", "America/New_York", now)]}


async def _calendar_forexfactory(days: int = 7) -> dict[str, Any]:
    """Public Forex Factory calendar with ALL currencies and ALL impact levels."""
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"}) as client:
            response = await client.get(FOREX_FACTORY_CALENDAR_URL)
            response.raise_for_status()
            text = response.text.lstrip("\\ufeff")
    except Exception as exc:
        return {"mode": "error", "events": [], "warning": f"Forex Factory calendar request failed: {exc}"}

    try:
        sample = text[:4096]
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\\t")
    except Exception:
        dialect = csv.excel
    try:
        rows = list(csv.DictReader(io.StringIO(text), dialect=dialect))
    except Exception as exc:
        return {"mode": "error", "events": [], "warning": f"Forex Factory CSV parse failed: {exc}"}

    def get(row: dict, *names: str):
        lowered = {str(k).strip().lower(): v for k, v in row.items() if k is not None}
        for n in names:
            if n.lower() in lowered:
                return lowered[n.lower()]
        return None

    events=[]
    now=datetime.now(timezone.utc)
    max_dt=now+timedelta(days=days)
    london=ZoneInfo("Europe/London")
    for row in rows:
        currency=(get(row,"currency","curr") or "").strip().upper()
        event_name=(get(row,"event","title") or "").strip()
        if not currency or not event_name:
            continue
        impact=(get(row,"impact") or "").strip().upper() or "LOW"
        if impact not in {"HIGH","MEDIUM","LOW"}:
            impact="LOW"
        date_value=(get(row,"date") or "").strip()
        time_value=(get(row,"time") or "").strip()
        dt_iso=None
        if date_value and time_value:
            for fmt in ("%m-%d-%Y %I:%M%p","%Y-%m-%d %I:%M%p","%m/%d/%Y %I:%M%p"):
                try:
                    dt=datetime.strptime(f"{date_value} {time_value}",fmt).replace(tzinfo=london).astimezone(timezone.utc)
                    if dt < now-timedelta(days=1) or dt > max_dt:
                        continue
                    dt_iso=dt.isoformat(); break
                except ValueError:
                    pass
        events.append({
            "time":dt_iso or f"{date_value} {time_value}".strip(),
            "country":currency,
            "event":event_name,
            "impact":impact,
            "estimate":get(row,"forecast"),
            "forecast":get(row,"forecast"),
            "previous":get(row,"previous","prev"),
            "actual":get(row,"actual"),
            "unit":get(row,"unit"),
            "source":"Forex Factory",
        })
    events.sort(key=lambda x:str(x.get("time") or ""))
    return {"mode":"live","provider":"forexfactory","events":events,"warning":None if events else "Economic calendar events topilmadi."}

async def _calendar_tradingeconomics(days: int = 2) -> dict[str, Any]:
    if not TRADING_ECONOMICS_API_KEY:
        return {"mode": "unconfigured", "events": [], "warning": "TRADING_ECONOMICS_API_KEY is not configured."}
    start = datetime.now(timezone.utc).date()
    end = start + timedelta(days=days)
    url = "https://api.tradingeconomics.com/calendar/country/united%20states"
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            r = await client.get(url, params={"c": TRADING_ECONOMICS_API_KEY, "d1": start.isoformat(), "d2": end.isoformat(), "importance": 3})
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        return {"mode": "error", "events": [], "warning": f"Trading Economics calendar request failed: {exc}"}
    events = []
    for item in data if isinstance(data, list) else []:
        events.append({
            "time": item.get("Date"), "country": item.get("Country", "United States"),
            "event": item.get("Event"), "impact": "HIGH" if str(item.get("Importance")) == "3" else "MEDIUM",
            "estimate": item.get("Forecast"), "forecast": item.get("Forecast"), "previous": item.get("Previous"),
            "actual": item.get("Actual"), "unit": item.get("Unit"), "source": "Trading Economics",
        })
    return {"mode": "live", "provider": "tradingeconomics", "events": events, "warning": None if events else "No USD HIGH IMPACT events found."}

async def _calendar_finnhub(days: int) -> dict[str, Any]:
    start = datetime.now(timezone.utc).date()
    end = start + timedelta(days=days)
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(
                "https://finnhub.io/api/v1/calendar/economic",
                params={"from": start.isoformat(), "to": end.isoformat(), "token": FINNHUB_API_KEY},
            )
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        return {"mode": "error", "events": [], "warning": f"Finnhub calendar request failed: {exc}"}
    events = []
    for item in data.get("economicCalendar", []) or []:
        country = str(item.get("country", "")).upper()
        if country not in {"UNITED STATES", "US", "USA", "USD"}:
            continue
        impact = str(item.get("impact", "")).upper() or "UNKNOWN"
        events.append({
            "time": item.get("time"),
            "country": item.get("country") or "USD",
            "event": item.get("event"),
            "impact": impact,
            "estimate": item.get("estimate"),
            "forecast": item.get("estimate"),
            "previous": item.get("prev"),
            "actual": item.get("actual"),
            "unit": item.get("unit"),
            "source": "Finnhub",
        })
    events.sort(key=lambda x: str(x.get("time") or ""))
    return {"mode": "live", "provider": "finnhub", "events": events, "warning": None if events else "No USA/USD economic events found."}


async def economic_calendar(days: int = 7) -> dict[str, Any]:
    """TradingView Economic Calendar is embedded client-side; no API key or scrape is used."""
    return {"mode":"widget", "provider":"TradingView Economic Calendar", "events":[],
            "warning":None, "days":days,
            "message":"TradingView Economic Calendar widget provides the live global calendar."}


def next_candle_close(timestamp: int, interval: str, now_ts: float | None = None) -> int:
    seconds = TIMEFRAME_SECONDS[validate_interval(interval)]
    now_ts = now_ts if now_ts is not None else datetime.now(timezone.utc).timestamp()
    epoch = int(now_ts)
    return ((epoch // seconds) + 1) * seconds


def candle_countdown(interval: str) -> dict[str, Any]:
    interval = validate_interval(interval)
    now_ts = datetime.now(timezone.utc).timestamp()
    close_ts = next_candle_close(int(now_ts), interval, now_ts)
    remaining = max(0, close_ts - int(now_ts))
    total = TIMEFRAME_SECONDS[interval]
    return {"interval": interval, "seconds_remaining": int(remaining), "total_seconds": total, "close_timestamp": close_ts, "close_iso": datetime.fromtimestamp(close_ts, timezone.utc).isoformat()}


def news_blackout(events: list[dict[str, Any]]) -> tuple[bool, str | None]:
    now = datetime.now(timezone.utc)
    for event in events:
        if str(event.get("impact", "")).upper() != "HIGH":
            continue
        raw = event.get("time")
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            delta = abs((dt - now).total_seconds())
            if delta <= NEWS_BLACKOUT_MINUTES * 60:
                return True, f"HIGH IMPACT: {event.get('event', 'Economic release')} near {event.get('time')}."
        except ValueError:
            continue
    return False, None


def technical_analysis(candles_data: list[dict[str, Any]], levels: dict[str, Any], setup: dict[str, Any]) -> dict[str, Any]:
    current = candles_data[-1]["close"]
    r = rsi(candles_data)
    a = atr(candles_data)
    if r >= 70:
        rsi_state = "OVERBOUGHT"
    elif r <= 30:
        rsi_state = "OVERSOLD"
    else:
        rsi_state = "NEUTRAL"
    return {
        "rsi": round(r, 2), "rsi_state": rsi_state, "atr": round(a, 4),
        "pivot": levels["pivot"], "support": [levels["s1"], levels["s2"], levels["s3"]],
        "resistance": [levels["r1"], levels["r2"], levels["r3"]],
        "trend": levels["bias"], "signal": setup["signal"],
        "summary": f"RSI {r:.1f} ({rsi_state}); Pivot {levels['pivot']:.2f}; trend {levels['bias']}; setup {setup['setup']}.",
    }



async def calculate_pivot_for_interval(symbol: str, interval: str) -> tuple[dict[str, Any], str | None]:
    """Classic Pivot levels based on the previous completed candle of the selected timeframe.
    This intentionally does NOT force D1 for every timeframe.
    """
    interval = validate_interval(interval)
    source_interval = interval
    warning = None
    try:
        data, _, _ = await get_candles(symbol, interval, 80)
    except Exception as exc:
        # M30 is locally built from M15. If a very short timeframe is unavailable,
        # use M5 as an explicitly labelled fallback rather than returning empty levels.
        source_interval = "5min" if interval in {"1min", "30min"} else "1h"
        data, _, _ = await get_candles(symbol, source_interval, 80)
        warning = f"{interval} Pivot {source_interval} ma'lumotidan hisoblandi: {exc}"
    if interval == "30min" and source_interval == "30min":
        pass
    if len(data) < 2:
        raise MarketDataError(f"{interval} uchun Pivot hisoblashga yetarli candle yo'q")
    ref = data[-2]
    current = float(data[-1]["close"])
    levels = calculate_pivot_levels(float(ref["high"]), float(ref["low"]), float(ref["close"]), current)
    levels["timeframe"] = interval
    levels["source_timeframe"] = source_interval
    levels["reference_time"] = ref.get("time")
    levels["warning"] = warning
    return levels, warning

async def ai_smart_analysis(analysis_context: dict[str, Any]) -> dict[str, Any]:
    """OpenAI analysis with candle-level cache and request coalescing.

    The cache key is symbol/timeframe/candle_time, not the full mutable context.
    Therefore price ticks inside one candle never trigger another OpenAI request.
    A 429 is cached for that candle and the next request is allowed only after the
    candle timestamp changes.
    """
    symbol = str(analysis_context.get("symbol", "XAU/USD"))
    timeframe = str(analysis_context.get("timeframe", "5min"))
    candle_time = analysis_context.get("candle_time") or analysis_context.get("last_candle_time")
    cache_key = f"{symbol}|{timeframe}|{candle_time}"
    now = datetime.now(timezone.utc).timestamp()

    async with AI_LOCKS_GUARD:
        lock = AI_LOCKS.setdefault(cache_key, asyncio.Lock())

    async with lock:
        cached = AI_CACHE.get(cache_key)
        if cached:
            cached_at, cached_candle, cached_result = cached
            if cached_candle == str(candle_time) and now - cached_at < AI_CACHE_TTL:
                return dict(cached_result)

        prompt = (
            "You are a disciplined market-analysis assistant. Based ONLY on the supplied XAU/USD technical context, "
            "give a concise non-guaranteed trading analysis. Return JSON with keys: summary, bias, confidence, advice. "
            "Confidence must be an integer 0-100. Do not claim certainty or guaranteed profits.\n\n"
            + json.dumps(analysis_context, ensure_ascii=False, default=str)
        )
        if OPENAI_API_KEY:
            try:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=REQUEST_TIMEOUT, max_retries=0)
                response = await client.responses.create(model=OPENAI_MODEL, input=prompt)
                text = getattr(response, "output_text", "").strip()
                if text:
                    try:
                        parsed = json.loads(text)
                        result = {"mode": "openai", **parsed}
                    except json.JSONDecodeError:
                        result = {
                            "mode": "openai", "summary": text,
                            "bias": analysis_context.get("bias", "NEUTRAL"),
                            "confidence": int(analysis_context.get("confidence", 50)),
                            "advice": "Use the key levels and wait for candle confirmation."
                        }
                    AI_CACHE[cache_key] = (now, str(candle_time), result)
                    return result
            except Exception as exc:
                msg = str(exc)
                if "429" in msg or "rate limit" in msg.lower():
                    result = {
                        "mode": "rate_limited", "warning": "OpenAI rate limit (429).",
                        "summary": "OpenAI 429: natija shu candle uchun cache qilindi; keyingi candle'da qayta tekshiriladi.",
                        "bias": analysis_context.get("bias", "NEUTRAL"),
                        "confidence": 0,
                        "advice": "Keyingi candle ochilganda OpenAI avtomatik qayta tekshiriladi."
                    }
                else:
                    result = {"mode": "fallback", "warning": f"AI provider unavailable: {msg}", "summary": "OpenAI vaqtincha mavjud emas.", "bias": analysis_context.get("bias", "NEUTRAL"), "confidence": 0, "advice": "Keyingi candle'da qayta tekshiriladi."}
                AI_CACHE[cache_key] = (now, str(candle_time), result)
                return result

        bias = analysis_context.get("bias", "NEUTRAL")
        mtf = analysis_context.get("mtf_overall", "MIXED")
        r = float(analysis_context.get("rsi", 50))
        direction = analysis_context.get("signal", "WAIT")
        confidence = 50
        if direction in ("BUY", "SELL"):
            confidence += 15
        if (bias == "BULLISH" and mtf == "BULLISH") or (bias == "BEARISH" and mtf == "BEARISH"):
            confidence += 20
        if r > 70 or r < 30:
            confidence -= 5
        confidence = max(35, min(confidence, 92))
        result = {
            "mode": "rule_based",
            "summary": f"{bias} Pivot bias with {mtf} multi-timeframe context. Current setup: {direction}.",
            "bias": bias, "confidence": confidence,
            "advice": "Follow Pivot direction, wait for confirmed retest/breakout, and avoid entries around HIGH IMPACT news.",
        }
        AI_CACHE[cache_key] = (now, str(candle_time), result)
        return result



def _swing_points(candles: list[dict[str, Any]], left: int = 2, right: int = 2) -> tuple[list[tuple[int,float]], list[tuple[int,float]]]:
    highs=[]; lows=[]
    n=len(candles)
    for i in range(left, n-right):
        hi=float(candles[i]["high"]); lo=float(candles[i]["low"])
        if hi >= max(float(candles[j]["high"]) for j in range(i-left,i+right+1)):
            highs.append((i,hi))
        if lo <= min(float(candles[j]["low"]) for j in range(i-left,i+right+1)):
            lows.append((i,lo))
    return highs, lows


def _linear_slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    n=len(values); xm=(n-1)/2
    ym=sum(values)/n
    den=sum((i-xm)**2 for i in range(n)) or 1.0
    return sum((i-xm)*(v-ym) for i,v in enumerate(values))/den


def _detect_fvg(candles: list[dict[str, Any]]) -> dict[str, Any]:
    # 3-candle imbalance: bullish when current low > two-bars-ago high; bearish vice versa.
    for i in range(len(candles)-1, 1, -1):
        a,b,c=candles[i-2],candles[i-1],candles[i]
        if float(c["low"]) > float(a["high"]):
            return {"type":"BULLISH","low":round(float(a["high"]),4),"high":round(float(c["low"]),4),"index":i}
        if float(c["high"]) < float(a["low"]):
            return {"type":"BEARISH","low":round(float(c["high"]),4),"high":round(float(a["low"]),4),"index":i}
    return {"type":"NONE","low":None,"high":None,"index":None}


def _detect_order_block(candles: list[dict[str, Any]], atr_value: float) -> dict[str, Any]:
    # Last opposite candle before a displacement move.
    for i in range(len(candles)-1, 2, -1):
        prev=candles[i-1]; cur=candles[i]
        body=abs(float(cur["close"])-float(cur["open"]))
        if body < atr_value*0.9:
            continue
        if float(cur["close"]) > float(cur["open"]) and float(prev["close"]) < float(prev["open"]):
            return {"type":"BULLISH","low":round(float(prev["low"]),4),"high":round(float(prev["high"]),4),"index":i-1}
        if float(cur["close"]) < float(cur["open"]) and float(prev["close"]) > float(prev["open"]):
            return {"type":"BEARISH","low":round(float(prev["low"]),4),"high":round(float(prev["high"]),4),"index":i-1}
    return {"type":"NONE","low":None,"high":None,"index":None}


def _detect_liquidity(candles: list[dict[str, Any]], highs: list[tuple[int,float]], lows: list[tuple[int,float]]) -> dict[str, Any]:
    last=candles[-1]
    recent_high=max((x[1] for x in highs[-8:]), default=float(last["high"]))
    recent_low=min((x[1] for x in lows[-8:]), default=float(last["low"]))
    sweep_high=float(last["high"]) > recent_high and float(last["close"]) < recent_high
    sweep_low=float(last["low"]) < recent_low and float(last["close"]) > recent_low
    return {"type":"BUY_SIDE_SWEEP" if sweep_high else "SELL_SIDE_SWEEP" if sweep_low else "NONE","high":round(recent_high,4),"low":round(recent_low,4)}


def _structure_state(candles: list[dict[str, Any]]) -> dict[str, Any]:
    highs,lows=_swing_points(candles)
    last=candles[-1]
    recent_high=highs[-1][1] if highs else float(last["high"])
    recent_low=lows[-1][1] if lows else float(last["low"])
    prev_high=highs[-2][1] if len(highs)>1 else recent_high
    prev_low=lows[-2][1] if len(lows)>1 else recent_low
    close=float(last["close"])
    bos="BULLISH" if close > recent_high else "BEARISH" if close < recent_low else "NONE"
    # CHOCH: current break contradicts prior swing sequence.
    prior="BULLISH" if recent_high >= prev_high and recent_low >= prev_low else "BEARISH" if recent_high <= prev_high and recent_low <= prev_low else "MIXED"
    choch="NONE"
    if prior=="BEARISH" and close>recent_high: choch="BULLISH"
    elif prior=="BULLISH" and close<recent_low: choch="BEARISH"
    internal_high=max((float(c["high"]) for c in candles[-8:]),default=recent_high)
    internal_low=min((float(c["low"]) for c in candles[-8:]),default=recent_low)
    internal="BULLISH" if close>internal_high*0.9999 else "BEARISH" if close<internal_low*1.0001 else "RANGE"
    return {"bos":bos,"choch":choch,"prior_structure":prior,"internal_structure":internal,"swing_high":round(recent_high,4),"swing_low":round(recent_low,4)}


def _snr(candles: list[dict[str, Any]]) -> dict[str, Any]:
    highs,lows=_swing_points(candles,2,2)
    resistance=max((x[1] for x in highs[-12:]), default=float(candles[-1]["high"]))
    support=min((x[1] for x in lows[-12:]), default=float(candles[-1]["low"]))
    return {"support":round(support,4),"resistance":round(resistance,4)}


def _snr_malaysia(candles: list[dict[str, Any]]) -> dict[str, Any]:
    # Session SNR using Kuala Lumpur daytime (08:00–17:00 local) of recent candles.
    highs=[]; lows=[]
    for c in candles[-240:]:
        dt=datetime.fromtimestamp(c["time"], timezone.utc).astimezone(ZoneInfo("Asia/Kuala_Lumpur"))
        if dt.weekday()<5 and 8 <= dt.hour < 17:
            highs.append(float(c["high"])); lows.append(float(c["low"]))
    if not highs:
        return {"support":None,"resistance":None,"session":"Malaysia 08:00–17:00"}
    return {"support":round(min(lows),4),"resistance":round(max(highs),4),"session":"Malaysia 08:00–17:00"}


def build_advanced_signal(candles: list[dict[str, Any]], interval: str, news_blocked: bool=False) -> dict[str, Any]:
    current=float(candles[-1]["close"])
    avtr=max(atr(candles), current*0.0004)
    snr=_snr(candles); msnr=_snr_malaysia(candles)
    structure=_structure_state(candles)
    fvg=_detect_fvg(candles)
    ob=_detect_order_block(candles,avtr)
    highs,lows=_swing_points(candles)
    liq=_detect_liquidity(candles,highs,lows)
    closes=[float(c["close"]) for c in candles]
    fast=closes[-50:]
    global_window=closes[-200:] if len(closes)>=200 else closes
    trend_slope=_linear_slope(fast)
    global_slope=_linear_slope(global_window)
    trend="BULLISH" if trend_slope>0 else "BEARISH" if trend_slope<0 else "NEUTRAL"
    global_trend="BULLISH" if global_slope>0 else "BEARISH" if global_slope<0 else "NEUTRAL"
    r=rsi(candles); 
    ict_bias=0
    reasons=[]
    # ICT-style confluence (liquidity + displacement/order block + FVG + structure).
    if liq["type"]=="SELL_SIDE_SWEEP": ict_bias+=2; reasons.append("sell-side liquidity sweep")
    elif liq["type"]=="BUY_SIDE_SWEEP": ict_bias-=2; reasons.append("buy-side liquidity sweep")
    if ob["type"]=="BULLISH": ict_bias+=1; reasons.append("bullish order block")
    elif ob["type"]=="BEARISH": ict_bias-=1; reasons.append("bearish order block")
    if fvg["type"]=="BULLISH": ict_bias+=1; reasons.append("bullish FVG")
    elif fvg["type"]=="BEARISH": ict_bias-=1; reasons.append("bearish FVG")
    if structure["bos"]=="BULLISH": ict_bias+=2; reasons.append("BOS bullish")
    elif structure["bos"]=="BEARISH": ict_bias-=2; reasons.append("BOS bearish")
    if structure["choch"]=="BULLISH": ict_bias+=2; reasons.append("CHOCH bullish")
    elif structure["choch"]=="BEARISH": ict_bias-=2; reasons.append("CHOCH bearish")
    if structure["internal_structure"]=="BULLISH": ict_bias+=1
    elif structure["internal_structure"]=="BEARISH": ict_bias-=1
    score=ict_bias
    if trend=="BULLISH": score+=2
    elif trend=="BEARISH": score-=2
    if global_trend=="BULLISH": score+=2
    elif global_trend=="BEARISH": score-=2
    if snr["resistance"]>current and current>snr["support"]:
        reasons.append("SNR range context")
    if msnr["resistance"] and msnr["support"] and msnr["support"]<current<msnr["resistance"]:
        reasons.append("Malaysia SNR range context")
    if r>=55: score+=1
    elif r<=45: score-=1
    # Explicit SNR breakout bonus/penalty.
    if current>snr["resistance"]: score+=2; reasons.append("SNR resistance breakout")
    elif current<snr["support"]: score-=2; reasons.append("SNR support breakdown")
    if msnr["resistance"] and current>msnr["resistance"]: score+=1; reasons.append("Malaysia SNR resistance break")
    elif msnr["support"] and current<msnr["support"]: score-=1; reasons.append("Malaysia SNR support break")

    confidence=min(99,max(35,50+abs(score)*5))
    direction="BUY" if score>=6 else "SELL" if score<=-6 else "WAIT"
    if news_blocked: direction="WAIT"
    entry=current
    swing_low=structure["swing_low"]; swing_high=structure["swing_high"]
    if direction=="BUY":
        sl=min(swing_low, current-avtr*1.2); risk=max(entry-sl,avtr*0.6); tp=[entry+risk*1.5,entry+risk*2.5]
    elif direction=="SELL":
        sl=max(swing_high, current+avtr*1.2); risk=max(sl-entry,avtr*0.6); tp=[entry-risk*1.5,entry-risk*2.5]
    else:
        sl=None; tp=[]
    setup="ICT+SNR+CONFLUENCE" if direction!="WAIT" else ("NEWS_BLACKOUT" if news_blocked else "WAIT_CONFLUENCE")
    return {
        "interval":interval,"signal":direction,"entry":round(entry,4),"stop_loss":round(sl,4) if sl is not None else None,
        "take_profit":[round(x,4) for x in tp],"confidence":confidence,"score":score,"setup":setup,
        "components":{"ICT":ict_bias,"SNR":snr,"SNR Malaysia":msnr,"Order Block":ob,"FVG":fvg,"Liquidity":liq,
                       "Trend Line":trend,"Global Trend Line":global_trend,"BOS":structure["bos"],"CHOCH":structure["choch"],"Internal Structure":structure["internal_structure"]},
        "reason":("; ".join(dict.fromkeys(reasons)) or "No strong confluence") + ("; news blackout active" if news_blocked else ""),
        "rsi":round(r,2),"atr":round(avtr,4),"current_price":round(current,4),
        "evaluated_at":datetime.now(timezone.utc).isoformat()
    }


async def build_advanced_signals(symbol: str, news_blocked: bool=False) -> dict[str, Any]:
    # RealMarketAPI's documented analysis timeframes. M30 is built locally from M15.
    intervals=["1min","5min","15min","30min","1h","4h","1day"]
    async def one(tf: str):
        try:
            candles_data,mode,warning=await get_candles(symbol,tf,260)
            item=build_advanced_signal(candles_data,tf,news_blocked=news_blocked)
            # Every timeframe and signal component is calculated from the same
            # TradingView OHLC series returned by get_candles(). No secondary
            # market-data or provider-intelligence result is merged into the signal.
            return tf,{**item,"mode":mode,"warning":warning}
        except Exception as exc:
            return tf,{"interval":tf,"signal":"UNAVAILABLE","entry":None,"stop_loss":None,"take_profit":[],
                       "confidence":0,"score":0,"setup":"ERROR","components":{},
                       "reason":str(exc),"mode":"error","warning":str(exc)}
    pairs=await asyncio.gather(*(one(tf) for tf in intervals))
    return {"symbol":clean_symbol(symbol),"timeframes":{tf:data for tf,data in pairs},
            "generated_at":datetime.now(timezone.utc).isoformat()}




async def book_openai_second_opinion(symbol: str, interval: str) -> dict[str, Any]:
    """Book-pattern result + OpenAI second opinion using the same live candle feed.

    OpenAI is intentionally called even when Book currently says WAIT, so the UI
    can show the independent second opinion. To prevent 429 bursts, the result is
    cached per symbol/timeframe/candle and concurrent requests are coalesced.
    """
    symbol = clean_symbol(symbol)
    interval = validate_interval(interval)
    candles_data, mode, warning = await get_candles(symbol, interval, 220)
    if len(candles_data) < 40:
        raise MarketDataError(f"{interval} uchun kitob pattern analizi uchun yetarli candle mavjud emas")

    book = book_signal(candles_data)
    last_candle_time = candles_data[-1].get("time")
    cache_key = f"{symbol}|{interval}"

    async with BOOK_OPENAI_LOCKS_GUARD:
        lock = BOOK_OPENAI_LOCKS.setdefault(cache_key, asyncio.Lock())

    async with lock:
        now = datetime.now(timezone.utc).timestamp()
        cached = BOOK_OPENAI_CACHE.get(cache_key)
        if cached:
            cached_at, cached_candle_time, cached_ai = cached
            # Reuse the exact same AI result while the current candle is unchanged.
            if cached_candle_time == last_candle_time and now - cached_at < BOOK_OPENAI_CACHE_TTL:
                ai = dict(cached_ai)
            else:
                ai = None
        else:
            ai = None

        context = {
            "symbol": symbol,
            "timeframe": interval,
            "current_price": candles_data[-1]["close"],
            "book_signal": book["signal"],
            "book_reason": book["reason"],
            "book_patterns": book["patterns"],
            "recent_candles": candles_data[-80:],
            "rule": "Validate ONLY the supplied SIMPLE TRADING Book pattern result and supplied OHLC candles. You may return BUY, SELL or WAIT. Do not invent ICT, FVG, order blocks, liquidity, RSI, MACD, or other strategies.",
        }

        if ai is None:
            ai = {"signal": "WAIT", "confidence": 0, "reason": "OpenAI unavailable.", "mode": "fallback"}
            if OPENAI_API_KEY:
                try:
                    from openai import AsyncOpenAI
                    client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=REQUEST_TIMEOUT, max_retries=0)
                    prompt = (
                        "You are the second-opinion validator for XAU/USD. "
                        "Use ONLY the supplied SIMPLE TRADING Book pattern result and recent OHLC candles. "
                        "Even if the Book signal is WAIT, still evaluate the supplied Book patterns and candles and return your own second opinion as BUY, SELL, or WAIT. "
                        "Do not add ICT, FVG, order blocks, liquidity, RSI, MACD, or any other strategy. "
                        "Return JSON only with keys signal (BUY/SELL/WAIT), confidence (0-100 integer), reason (short). "
                        "Do not invent price data.\n\n" +
                        json.dumps(context, ensure_ascii=False, default=str)
                    )
                    response = await client.responses.create(model=OPENAI_MODEL, input=prompt)
                    text = getattr(response, "output_text", "").strip()
                    if text:
                        try:
                            parsed = json.loads(text)
                            sig = str(parsed.get("signal", "WAIT")).upper()
                            ai = {
                                "signal": sig if sig in {"BUY", "SELL", "WAIT"} else "WAIT",
                                "confidence": max(0, min(100, int(parsed.get("confidence", 0)))),
                                "reason": str(parsed.get("reason", "OpenAI second opinion.")),
                                "mode": "openai",
                            }
                        except Exception:
                            ai = {"signal": "WAIT", "confidence": 0, "reason": "OpenAI returned an invalid structured result.", "mode": "openai"}
                except Exception as exc:
                    msg = str(exc)
                    if "429" in msg or "rate limit" in msg.lower():
                        ai = {"signal": "WAIT", "confidence": 0, "reason": "OpenAI rate limit (429). Natija shu candle uchun cache qilindi; shu candle davomida yangi so‘rov yuborilmaydi va keyingi candle'da qayta tekshiriladi.", "mode": "rate_limited"}
                    else:
                        ai = {"signal": "WAIT", "confidence": 0, "reason": f"OpenAI unavailable: {msg}", "mode": "fallback"}
            BOOK_OPENAI_CACHE[cache_key] = (now, last_candle_time, dict(ai))

    final_signal = book["signal"] if book["signal"] in {"BUY", "SELL"} and ai["signal"] == book["signal"] else "WAIT"
    price = float(candles_data[-1]["close"])
    atr_value = max(_atr_local(candles_data), price * 0.0002)
    if final_signal == "BUY":
        entry, sl, tp = price, price - 1.2 * atr_value, [price + 2.0 * atr_value, price + 3.0 * atr_value]
    elif final_signal == "SELL":
        entry, sl, tp = price, price + 1.2 * atr_value, [price - 2.0 * atr_value, price - 3.0 * atr_value]
    else:
        entry, sl, tp = None, None, []
    return {
        "ok": True, "symbol": symbol, "interval": interval, "mode": mode, "warning": warning,
        "current_price": round(price, 4), "book": book, "openai": ai,
        "signal": final_signal, "entry": round(entry, 4) if entry is not None else None,
        "stop_loss": round(sl, 4) if sl is not None else None,
        "take_profit": [round(x, 4) for x in tp],
        "candle": candles_data[-1], "candles": candles_data,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }



async def build_full_analysis(symbol: str, interval: str) -> dict[str, Any]:
    """Build the public dashboard analysis from ONE TradingView/OANDA OHLC source.

    No provider fallback is used here. Every market-derived field is calculated
    from the exact candles returned by get_candles(), which itself is backed by
    the shared TradingView cache.
    """
    symbol = clean_symbol(symbol)
    interval = validate_interval(interval)
    candles_data, mode, warning = await get_candles(symbol, interval, 220)
    if len(candles_data) < 40:
        raise MarketDataError("TradingView returned too few candles for analysis")

    # Previous completed candle of the SAME selected timeframe for classic pivots.
    if len(candles_data) >= 2:
        ref = candles_data[-2]
    else:
        ref = candles_data[-1]
    current_price = float(candles_data[-1]["close"])
    levels = calculate_pivot_levels(
        float(ref["high"]), float(ref["low"]), float(ref["close"]), current_price
    )
    levels.update({
        "timeframe": interval,
        "source_timeframe": interval,
        "reference_time": ref.get("time"),
        "warning": None,
    })
    setup = build_key_level_signal(candles_data, levels, news_blocked=False)
    technical = technical_analysis(candles_data, levels, setup)

    # MTF is also TradingView-only. It is intentionally fetched separately because
    # each timeframe is a distinct TradingView series.
    mtf = await multi_timeframe(symbol)
    ai_context = {
        "symbol": symbol,
        "timeframe": interval,
        "candle_time": candles_data[-1].get("time"),
        "current_price": current_price,
        "bias": levels["bias"],
        "signal": setup["signal"],
        "setup": setup["setup"],
        "confidence": 50,
        "rsi": technical["rsi"],
        "mtf_overall": mtf.get("overall", "MIXED"),
        "pivot": levels["pivot"],
        "support": [levels["s1"], levels["s2"], levels["s3"]],
        "resistance": [levels["r1"], levels["r2"], levels["r3"]],
    }
    ai = await ai_smart_analysis(ai_context)
    return {
        "ok": True,
        "symbol": symbol,
        "interval": interval,
        "mode": mode,
        "warning": warning,
        "current_price": round(current_price, 4),
        "candles": candles_data,
        "candle": candles_data[-1],
        "levels": levels,
        "technical": technical,
        "setup": setup,
        "direction": setup["signal"],
        "headline": f"{setup['signal']} · {setup['setup']}",
        "multi_timeframe": mtf,
        "ai_smart": ai,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/candles/{symbol:path}")
async def candles_endpoint(symbol: str, interval: str = Query(DEFAULT_INTERVAL), limit: int = Query(220, ge=2, le=500)) -> dict[str, Any]:
    """Canonical candle endpoint: TradingView/OANDA only."""
    interval = validate_interval(interval)
    try:
        rows = await fetch_tradingview_candles(clean_symbol(symbol), interval, limit)
        if not rows:
            raise MarketDataError("TradingView returned no candles")
        return {
            "ok": True,
            "symbol": clean_symbol(symbol),
            "interval": interval,
            "mode": "live",
            "provider": "TradingView",
            "source": TRADINGVIEW_SYMBOL,
            "candles": rows,
            "candle": rows[-1],
            "warning": None,
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"TradingView candles unavailable: {exc}")


@app.get("/api/v1/book-openai-analysis/{symbol:path}")
async def get_book_openai_analysis(symbol: str, interval: str = Query(DEFAULT_INTERVAL)) -> dict[str, Any]:
    try:
        return await book_openai_second_opinion(clean_symbol(symbol), validate_interval(interval))
    except Exception as exc:
        return {"ok": False, "symbol": clean_symbol(symbol), "interval": validate_interval(interval),
                "signal": "WAIT", "entry": None, "stop_loss": None, "take_profit": [],
                "book": {"signal": "WAIT", "patterns": [], "reason": str(exc)},
                "openai": {"signal": "WAIT", "confidence": 0, "reason": str(exc), "mode": "fallback"},
                "error": str(exc)}


@app.get("/api/v1/quote/{symbol:path}")
async def quote(symbol: str, interval: str = Query(DEFAULT_INTERVAL)) -> dict[str, Any]:
    """Canonical quote from the same TradingView OANDA:XAUUSD chart series."""
    symbol = clean_symbol(symbol)
    interval = validate_interval(interval)
    try:
        price, source = await fetch_live_price_any(symbol, interval)
        bars = await fetch_tradingview_candles(symbol, interval, 2)
        ts = int(bars[-1]["time"]) if bars else int(datetime.now(timezone.utc).timestamp())
        return {
            "symbol": symbol, "price": round(float(price), 4), "mode": "live",
            "provider": source, "timestamp": datetime.fromtimestamp(ts, timezone.utc).isoformat(),
            "source": "TradingView OANDA:XAUUSD chart series",
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail="TradingView live quote unavailable: " + str(exc))


@app.get("/api/v1/pivots/{symbol:path}")
async def get_pivots(symbol: str, interval: str = Query(DEFAULT_INTERVAL)) -> dict[str, Any]:
    selected = validate_interval(interval)
    try:
        levels, warning = await calculate_pivot_for_interval(clean_symbol(symbol), selected)
        return {"symbol": clean_symbol(symbol), "selected": selected,
                "timeframes": {selected: levels}, "errors": {},
                "generated_at": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        return {"symbol": clean_symbol(symbol), "selected": selected,
                "timeframes": {}, "errors": {selected: str(exc)},
                "generated_at": datetime.now(timezone.utc).isoformat()}

@app.get("/api/v1/ai-smart-analysis/{symbol:path}")
async def get_ai_smart_analysis(symbol: str, interval: str = Query(DEFAULT_INTERVAL)) -> dict[str, Any]:
    try:
        analysis = await build_full_analysis(clean_symbol(symbol), validate_interval(interval))
        ai = analysis.get("ai_smart") or {}
        return {"ok": True, "symbol": analysis["symbol"], "interval": analysis["interval"],
                "current_price": analysis["current_price"], "direction": analysis["direction"],
                "levels": analysis["levels"], "technical": analysis["technical"],
                "multi_timeframe": analysis["multi_timeframe"], "ai": ai,
                "generated_at": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        return {"ok": False, "interval": validate_interval(interval), "error": str(exc),
                "ai": {"mode":"fallback","summary":"AI Smart Analysis uchun backend ma'lumoti yetarli emas.",
                       "bias":"NEUTRAL","confidence":0,"advice":"Market data/API sozlamalarini tekshiring."}}

@app.get("/api/v1/analysis/{symbol:path}")
async def get_analysis(symbol: str, interval: str = Query(DEFAULT_INTERVAL)) -> dict[str, Any]:
    """Technical analysis from the canonical TradingView/OANDA candle series only."""
    symbol = clean_symbol(symbol)
    interval = validate_interval(interval)
    try:
        candles_data = await fetch_tradingview_candles(symbol, interval, 220)
        if len(candles_data) < 35:
            raise MarketDataError("TradingView candles yetarli emas")
        levels, _ = await calculate_pivot_for_interval(symbol, interval)
        setup = build_key_level_signal(candles_data, levels, news_blocked=False)
        technical = technical_analysis(candles_data, levels, setup)
        return {
            "ok": True, "symbol": symbol, "interval": interval, "mode": "tradingview",
            "provider": "TradingView", "source": TRADINGVIEW_SYMBOL,
            "current_price": round(float(candles_data[-1]["close"]), 4),
            "candles": candles_data, "levels": levels, "technical": technical,
            "setup": setup, "direction": setup.get("signal", "WAIT"),
            "headline": f"{setup.get('signal','WAIT')} · {setup.get('setup','WAIT')}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        return {"ok": False, "symbol": symbol, "interval": interval, "mode": "error",
                "error": str(exc), "technical": {}, "levels": {}, "setup": {"signal":"WAIT"},
                "direction": "WAIT", "generated_at": datetime.now(timezone.utc).isoformat()}

@app.get("/api/v1/multi-timeframe/{symbol:path}")
async def get_mtf(symbol: str) -> dict[str, Any]:
    try:
        return await multi_timeframe(clean_symbol(symbol))
    except Exception as exc:
        # Never turn an MTF panel failure into HTTP 500.
        return {"timeframes": {}, "overall": "UNAVAILABLE", "bullish_count": 0, "bearish_count": 0,
                "available_count": 0, "errors": {"global": f"{type(exc).__name__}: {exc}"}, "mode": "tradingview",
                "generated_at": datetime.now(timezone.utc).isoformat()}


@app.get("/api/v1/sessions")
async def get_sessions() -> dict[str, Any]:
    return await market_sessions()


@app.get("/api/v1/calendar")
async def get_calendar(days: int = Query(7, ge=1, le=14)) -> dict[str, Any]:
    return await economic_calendar(days)


@app.get("/api/v1/candle-countdown")
async def get_countdown(interval: str = Query(DEFAULT_INTERVAL)) -> dict[str, Any]:
    return candle_countdown(interval)



async def refresh_signal_outcomes(session: Session, user_id: int, limit: int = 100) -> list[SignalHistory]:
    """Refresh open paper trades using the same TradingView/OANDA:XAUUSD candles.

    Every auto/manual signal remains in the database. When TP1 or SL is touched,
    the row is closed and its payload receives result price/type and exact duration.
    If both TP1 and SL are touched inside one candle, the result is marked AMBIGUOUS
    rather than guessing which level was hit first.
    """
    rows = list(session.scalars(
        select(SignalHistory).where(
            SignalHistory.user_id == user_id,
            SignalHistory.outcome == "OPEN"
        ).order_by(SignalHistory.created_at.asc()).limit(limit)
    ))
    if not rows:
        return list(session.scalars(
            select(SignalHistory).where(SignalHistory.user_id == user_id)
            .order_by(SignalHistory.created_at.asc()).limit(limit)
        ))

    cache: dict[str, list[dict[str, Any]]] = {}
    changed = False
    for row in rows:
        try:
            payload = json.loads(row.payload or "{}")
        except Exception:
            payload = {}
        setup = payload.get("setup") or {}
        # Backward compatibility with advanced payloads.
        if not setup:
            adv = payload.get("advanced") or payload.get("signal") or {}
            setup = {
                "entry": adv.get("entry", row.price),
                "stop_loss": adv.get("stop_loss"),
                "take_profit": adv.get("take_profit", []),
            }
        entry = setup.get("entry", row.price)
        sl = setup.get("stop_loss")
        tps = setup.get("take_profit") or []
        try:
            entry = float(entry)
            sl = float(sl) if sl is not None else None
            tp1 = float(tps[0]) if tps else None
        except Exception:
            continue
        if sl is None or tp1 is None or row.direction not in ("BUY", "SELL"):
            continue

        tf = validate_interval(row.interval)
        if tf not in cache:
            try:
                candles, _, _ = await get_candles(row.symbol, tf, 260)
                cache[tf] = candles
            except Exception:
                cache[tf] = []
        candles = cache[tf]
        if not candles:
            continue

        created = row.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        result = None
        result_price = None
        result_candle_time = None
        for c in candles:
            ct = c.get("time")
            try:
                cdt = datetime.fromtimestamp(float(ct), tz=timezone.utc) if isinstance(ct, (int, float)) else datetime.fromisoformat(str(ct).replace("Z", "+00:00"))
            except Exception:
                continue
            if cdt <= created:
                continue
            high = float(c.get("high"))
            low = float(c.get("low"))
            if row.direction == "BUY":
                hit_tp = high >= tp1
                hit_sl = low <= sl
            else:
                hit_tp = low <= tp1
                hit_sl = high >= sl
            if hit_tp and hit_sl:
                result = "AMBIGUOUS"
                # Keep the candle close as an auditable reference; do not invent order.
                result_price = float(c.get("close"))
                result_candle_time = cdt
                break
            if hit_tp:
                result = "TP HIT"
                result_price = tp1
                result_candle_time = cdt
                break
            if hit_sl:
                result = "SL HIT"
                result_price = sl
                result_candle_time = cdt
                break

        if result and result_candle_time:
            duration = max(0, int((result_candle_time - created).total_seconds()))
            payload["result"] = {
                "type": result,
                "price": round(result_price, 4) if result_price is not None else None,
                "candle_time": result_candle_time.isoformat(),
                "duration_seconds": duration,
                "duration_minutes": round(duration / 60, 2),
            }
            payload["trade_status"] = "CLOSED"
            row.payload = json.dumps(payload, ensure_ascii=False)
            row.outcome = result
            row.closed_at = result_candle_time
            changed = True

    if changed:
        session.commit()
    return list(session.scalars(
        select(SignalHistory).where(SignalHistory.user_id == user_id)
        .order_by(SignalHistory.created_at.asc()).limit(limit)
    ))


@app.get("/api/v1/signals/advanced/{symbol:path}")
async def advanced_signals(symbol: str, authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    key = clean_symbol(symbol)
    now = asyncio.get_running_loop().time()
    cached = ADVANCED_SIGNAL_CACHE.get(key)
    if cached and now - cached[0] < ADVANCED_CACHE_TTL:
        return cached[1]
    # Economic calendar blackout is kept separate from signal calculation here;
    # the UI must always be able to obtain the latest market-derived signal.
    result = await build_advanced_signals(key, news_blocked=False)
    ADVANCED_SIGNAL_CACHE[key] = (now, result)
    return result


@app.post("/api/v1/signals/auto-record")
async def auto_record_signals(symbol: str = DEFAULT_SYMBOL, authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    """Auto-enter paper trades only when Signal Lab confidence is strictly > 85%."""
    user = current_user(authorization, session)
    key = clean_symbol(symbol)
    # First close any previously opened auto trades using fresh TradingView candles.
    await refresh_signal_outcomes(session, user.id, limit=500)
    if not AUTO_ENTRY_ENABLED:
        return {"enabled": False, "threshold": AUTO_ENTRY_THRESHOLD, "count": 0, "saved_timeframes": [], "mode": "paper"}

    result = await build_advanced_signals(key, news_blocked=False)
    now = datetime.now(timezone.utc)
    created = []
    for tf, item in result.get("timeframes", {}).items():
        direction = item.get("signal")
        confidence = float(item.get("confidence") or 0)
        entry = item.get("entry")
        sl = item.get("stop_loss")
        tp = item.get("take_profit") or []
        if direction not in ("BUY", "SELL") or confidence <= AUTO_ENTRY_THRESHOLD or entry is None or sl is None or not tp:
            continue

        # One open auto-trade per timeframe. A new trade is allowed after the previous
        # one is closed, even if the direction is unchanged.
        recent_open = session.scalars(select(SignalHistory).where(
            SignalHistory.user_id == user.id,
            SignalHistory.symbol == key,
            SignalHistory.interval == tf,
            SignalHistory.outcome == "OPEN",
        ).order_by(SignalHistory.created_at.desc())).first()
        if recent_open:
            continue

        # Avoid duplicate entries from repeated browser polling on the same candle.
        recent = session.scalars(select(SignalHistory).where(
            SignalHistory.user_id == user.id,
            SignalHistory.symbol == key,
            SignalHistory.interval == tf,
        ).order_by(SignalHistory.created_at.desc())).first()
        if recent:
            rcreated = recent.created_at
            if rcreated.tzinfo is None:
                rcreated = rcreated.replace(tzinfo=timezone.utc)
            if (now - rcreated).total_seconds() < AUTO_ENTRY_DUPLICATE_MINUTES * 60:
                continue

        trade_payload = {
            "trade_status": "OPEN",
            "entry": float(entry),
            "stop_loss": float(sl),
            "take_profit": [float(x) for x in tp],
            "signal": item,
            "mode": "paper_auto_entry",
            "source": "TradingView OANDA:XAUUSD candle series",
            "auto_entry": True,
            "confidence_threshold": AUTO_ENTRY_THRESHOLD,
            "confidence_at_entry": confidence,
            "entry_time": now.isoformat(),
        }
        row = SignalHistory(
            user_id=user.id, symbol=key, interval=tf, direction=direction,
            headline=f"AUTO ENTRY {direction} • {tf.upper()} • {confidence:.1f}%",
            price=float(entry), payload=json.dumps({"setup": {"entry": float(entry), "stop_loss": float(sl), "take_profit": [float(x) for x in tp]}, **trade_payload}, ensure_ascii=False),
            outcome="OPEN", created_at=now
        )
        session.add(row)
        created.append({"interval": tf, "direction": direction, "confidence": confidence, "entry": float(entry), "sl": float(sl), "tp": [float(x) for x in tp]})

    if created:
        session.commit()
    rows = await refresh_signal_outcomes(session, user.id, limit=500)
    return {"enabled": True, "threshold": AUTO_ENTRY_THRESHOLD, "saved_timeframes": [x["interval"] for x in created], "trades": created, "count": len(created), "history_count": len(rows), "mode": "paper_auto_entry"}


@app.get("/api/v1/signals/live/{symbol:path}")
async def live_signals(symbol: str) -> dict[str, Any]:
    # Every request recomputes signals from the current live candle feed.
    # No demo/static signal data is used.
    result = await build_advanced_signals(clean_symbol(symbol), news_blocked=False)
    return {**result, "mode": "live", "source": f"TradingView {TRADINGVIEW_SYMBOL} chart series"}

@app.post("/api/v1/signals/save-advanced")
async def save_advanced_signal(interval: str = DEFAULT_INTERVAL, symbol: str = DEFAULT_SYMBOL, authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    user = current_user(authorization, session)
    interval = validate_interval(interval)
    candles_data, mode, warning = await get_candles(clean_symbol(symbol), interval, 260)
    item = {**build_advanced_signal(candles_data, interval, news_blocked=False), "mode":mode, "warning":warning}
    if not item or item.get("signal") not in ("BUY","SELL"):
        raise HTTPException(status_code=400, detail="Bu timeframe uchun tasdiqlangan BUY/SELL signal mavjud emas.")
    row = SignalHistory(user_id=user.id, symbol=clean_symbol(symbol), interval=interval, direction=item["signal"], headline=f'{item["signal"]} • {item["setup"]}', price=float(item["entry"]), payload=json.dumps({"advanced":item,"setup":{"entry":item.get("entry"),"stop_loss":item.get("stop_loss"),"take_profit":item.get("take_profit",[])},"symbol":clean_symbol(symbol),"interval":interval}), outcome="OPEN", created_at=datetime.now(timezone.utc))
    session.add(row); session.commit(); session.refresh(row)
    return {"saved":True,"id":row.id,"signal":item}


@app.get("/api/v1/signals/analytics")
async def signal_analytics(authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    user = current_user(authorization, session)
    rows = await refresh_signal_outcomes(session, user.id)
    wins = sum(1 for r in rows if r.outcome == "TP HIT")
    losses = sum(1 for r in rows if r.outcome == "SL HIT")
    completed = wins + losses
    winrate = round((wins / completed) * 100, 2) if completed else 0.0
    by_tf: dict[str, dict[str, Any]] = {}
    for r in rows:
        item = by_tf.setdefault(r.interval, {"total_signals":0,"completed_trades":0,"wins":0,"losses":0,"winrate":0.0})
        item["total_signals"] += 1
        if r.outcome == "TP HIT": item["wins"] += 1
        elif r.outcome == "SL HIT": item["losses"] += 1
        item["completed_trades"] = item["wins"] + item["losses"]
        item["winrate"] = round(item["wins"] / item["completed_trades"] * 100, 2) if item["completed_trades"] else 0.0
    return {"total_signals": len(rows), "completed_trades": completed, "wins": wins, "losses": losses, "winrate": winrate, "open": sum(1 for r in rows if r.outcome == "OPEN"), "ambiguous": sum(1 for r in rows if r.outcome == "AMBIGUOUS"), "by_timeframe": by_tf}


@app.post("/api/v1/signals/save")
async def save_signal(symbol: str, interval: str = DEFAULT_INTERVAL, authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    user = current_user(authorization, session)
    analysis = await build_full_analysis(symbol, interval)
    item = SignalHistory(user_id=user.id, symbol=analysis["symbol"], interval=analysis["interval"], direction=analysis["direction"], headline=analysis["headline"], price=analysis["current_price"], payload=json.dumps(analysis), outcome="OPEN", created_at=datetime.now(timezone.utc))
    session.add(item); session.commit(); session.refresh(item)
    return {"id": item.id, "status": "saved", "outcome": item.outcome}


@app.get("/api/v1/signals/history")
async def signal_history(limit: int = Query(50, ge=1, le=100), authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    user = current_user(authorization, session)
    rows = await refresh_signal_outcomes(session, user.id, limit=100)
    rows = rows[-limit:][::-1]
    items = []
    for r in rows:
        payload = {}
        try: payload = json.loads(r.payload)
        except Exception: pass
        setup = payload.get("setup", {})
        result = payload.get("result", {}) or {}
        created_at = r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=timezone.utc)
        closed_at = r.closed_at if r.closed_at and r.closed_at.tzinfo else (r.closed_at.replace(tzinfo=timezone.utc) if r.closed_at else None)
        duration_seconds = result.get("duration_seconds")
        if duration_seconds is None and closed_at:
            duration_seconds = max(0, int((closed_at - created_at).total_seconds()))
        items.append({"id": r.id, "symbol": r.symbol, "interval": r.interval, "direction": r.direction, "entry": setup.get("entry", r.price), "tp": setup.get("take_profit", []), "sl": setup.get("stop_loss"), "headline": r.headline, "price": r.price, "outcome": r.outcome, "result_price": result.get("price"), "duration_seconds": duration_seconds, "duration_minutes": round(duration_seconds/60,2) if duration_seconds is not None else None, "auto_entry": bool(payload.get("auto_entry")), "confidence": payload.get("confidence_at_entry", payload.get("signal",{}).get("confidence")), "created_at": created_at.isoformat(), "closed_at": closed_at.isoformat() if closed_at else None})
    return {"items": items}


@app.get("/")
async def read_root() -> FileResponse:
    return FileResponse(os.path.join(BASE_DIR, "index.html"))
