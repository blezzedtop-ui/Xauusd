from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import asyncio
import smtplib
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
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

load_dotenv()

APP_TITLE = os.getenv("APP_TITLE", "Trading SaaS Analytics Platform")
MARKET_PROVIDER = os.getenv("MARKET_PROVIDER", "auto").lower()
REALMARKET_API_KEY = os.getenv("REALMARKET_API_KEY", "").strip()
REALMARKET_API_BASE = os.getenv("REALMARKET_API_BASE", "https://api.realmarketapi.com").strip().rstrip("/")
TWELVE_DATA_API_KEY = ""  # disabled: RealMarketAPI-only mode
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
AI_CACHE_TTL = int(os.getenv("AI_CACHE_TTL", "60"))
CANDLE_LIMIT = max(50, min(int(os.getenv("CANDLE_LIMIT", "220")), 500))
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "12"))
NODE_MARKET_URL = os.getenv("NODE_MARKET_URL", "http://127.0.0.1:3001").strip().rstrip("/")
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
AI_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
MARKET_HISTORY_CACHE: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}
MARKET_HISTORY_CACHE_TTL = int(os.getenv("MARKET_HISTORY_CACHE_TTL", "120"))


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
    # Current RealMarketAPI public FAQ documents /api/v1/history as H1 historical
    # candles. For other timeframes return recent real candles and let the UI show a
    # precise availability warning instead of a blank chart.
    if interval != "1h":
        return await fetch_realmarket_candles(symbol, interval, 10)
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
    errors=[]
    provider = live_provider()
    if provider == "yahoo":
        try:
            data = await fetch_yahoo_candles(symbol, interval, min(CANDLE_LIMIT, 500))
            return data, "live", "Yahoo Finance public market feed (XAUUSD or GC=F gold proxy; no API key)"
        except MarketDataError as exc:
            errors.append(str(exc))
    if REALMARKET_API_KEY:
        try:
            data = await fetch_realmarket_month_candles(symbol, interval, days)
            warning = None if interval == "1h" and len(data) > 10 else "RealMarketAPI provides recent candles for this timeframe; long-range /history is currently documented for H1."
            return data, "live", warning or "RealMarketAPI history"
        except MarketDataError as exc:
            errors.append(str(exc))
        try:
            data = await fetch_realmarket_candles(symbol, interval, min(CANDLE_LIMIT, 200))
            return data, "live", "RealMarketAPI recent candles"
        except MarketDataError as exc:
            errors.append(str(exc))
    raise MarketDataError("Live market history unavailable. " + " | ".join(errors))


async def fetch_realmarket_price(symbol: str) -> float:
    # RealMarketAPI /api/v1/price requires BOTH symbolCode and timeFrame.
    # The previous build omitted timeFrame, which caused HTTP 400 validation
    # errors and prevented quote/analysis/signal modules from receiving data.
    data = await rm_get("price", {
        "symbolCode": realmarket_symbol(symbol),
        "timeFrame": "M1",
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


async def get_candles(symbol: str, interval: str, limit: int) -> tuple[list[dict[str, Any]], str, str | None]:
    interval = validate_interval(interval)
    data, mode, provider = await get_chart_history(symbol, interval, max(31, 1))
    return data[-limit:], mode, provider


async def get_pivot_reference(symbol: str) -> tuple[dict[str, float], str | None]:
    try:
        data = await fetch_realmarket_candles(symbol, PIVOT_INTERVAL, 3)
        base = data[-2] if len(data) >= 2 else data[-1]
        return {"high":base["high"],"low":base["low"],"close":base["close"]}, None
    except Exception as exc:
        return {"high":0.0,"low":0.0,"close":0.0}, str(exc)


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
    out: dict[str, Any] = {}
    for tf in ("15min", "1h", "4h", "1day"):
        candles_data, mode, warning = await get_candles(symbol, tf, 80)
        out[tf] = {**timeframe_trend(candles_data), "mode": mode, "warning": warning}
    dirs = [out[x]["trend"] for x in out]
    score = dirs.count("BULLISH") - dirs.count("BEARISH")
    overall = "BULLISH" if score >= 2 else "BEARISH" if score <= -2 else "MIXED"
    return {"timeframes": out, "overall": overall, "bullish_count": dirs.count("BULLISH"), "bearish_count": dirs.count("BEARISH")}


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


async def _calendar_forexfactory(days: int = 2) -> dict[str, Any]:
    """Public weekly Forex Factory CSV fallback. Filtered to USD/high-impact events for XAUUSD relevance."""
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

    events = []
    now = datetime.now(timezone.utc)
    max_dt = now + timedelta(days=days)
    for row in rows:
        currency = (get(row, "currency", "curr") or "").strip().upper()
        impact = (get(row, "impact") or "").strip().upper()
        if currency not in {"USD", "US"}:
            continue
        # Forex Factory export marks impact as High/Medium/Low.
        if impact and impact != "HIGH":
            continue
        date_value = (get(row, "date") or "").strip()
        time_value = (get(row, "time") or "").strip()
        event_name = (get(row, "event", "title") or "").strip()
        actual = get(row, "actual")
        forecast = get(row, "forecast")
        previous = get(row, "previous", "prev")
        # Keep date/time as text when the feed gives approximate time; calendar consumers can still display it.
        dt_iso = None
        if date_value and time_value:
            for fmt in ("%m-%d-%Y %I:%M%p", "%Y-%m-%d %I:%M%p", "%m/%d/%Y %I:%M%p"):
                try:
                    dt = datetime.strptime(f"{date_value} {time_value}", fmt).replace(tzinfo=timezone.utc)
                    if dt < now - timedelta(days=1) or dt > max_dt:
                        continue
                    dt_iso = dt.isoformat()
                    break
                except ValueError:
                    pass
        if dt_iso is None and not event_name:
            continue
        events.append({
            "time": dt_iso or f"{date_value} {time_value}".strip(),
            "country": "United States",
            "event": event_name,
            "impact": "HIGH",
            "estimate": forecast,
            "forecast": forecast,
            "previous": previous,
            "actual": actual,
            "unit": get(row, "unit"),
            "source": "Forex Factory",
        })
    events.sort(key=lambda x: str(x.get("time") or ""))
    return {"mode": "live", "provider": "forexfactory", "events": events, "warning": None if events else "No USD HIGH IMPACT events found in the selected calendar window."}

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

async def economic_calendar(days: int = 2) -> dict[str, Any]:
    """Economic calendar with provider fallback: Trading Economics/Finnhub key, then public Forex Factory weekly export."""
    providers = []
    if CALENDAR_PROVIDER in {"tradingeconomics", "auto"} and TRADING_ECONOMICS_API_KEY:
        providers.append(_calendar_tradingeconomics)
    if CALENDAR_PROVIDER in {"finnhub", "auto"} and FINNHUB_API_KEY:
        providers.append(None)  # handled below to preserve the existing Finnhub implementation
    if CALENDAR_PROVIDER in {"forexfactory", "auto"}:
        providers.append(_calendar_forexfactory)

    if CALENDAR_PROVIDER == "finnhub" and FINNHUB_API_KEY:
        # Original Finnhub path.
        start = datetime.now(timezone.utc).date()
        end = start + timedelta(days=days)
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                response = await client.get("https://finnhub.io/api/v1/calendar/economic", params={"from": start.isoformat(), "to": end.isoformat(), "token": FINNHUB_API_KEY})
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            return {"mode": "error", "events": [], "warning": f"Finnhub calendar request failed: {exc}"}
        events=[]
        for item in data.get("economicCalendar", []) or []:
            impact = str(item.get("impact", "")).upper()
            if item.get("country", "").upper() not in {"UNITED STATES", "US", "USA"} or impact not in {"HIGH", "HIGH IMPACT"}:
                continue
            events.append({"time":item.get("time"),"country":item.get("country"),"event":item.get("event"),"impact":"HIGH","estimate":item.get("estimate"),"forecast":item.get("estimate"),"previous":item.get("prev"),"actual":item.get("actual"),"unit":item.get("unit"),"source":"Finnhub"})
        return {"mode":"live","provider":"finnhub","events":events,"warning":None if events else "No USD HIGH IMPACT events found."}

    for fn in providers:
        if fn is None:
            continue
        result = await fn(days)
        if result.get("events") or result.get("mode") == "live":
            return result
    return {"mode": "unavailable", "events": [], "warning": "Economic Calendar source is unavailable. Check internet access or configure a calendar API key."}


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


async def ai_smart_analysis(analysis_context: dict[str, Any]) -> dict[str, Any]:
    cache_key = json.dumps(analysis_context, sort_keys=True, default=str)
    now = datetime.now(timezone.utc).timestamp()
    cached = AI_CACHE.get(cache_key)
    if cached and now - cached[0] < AI_CACHE_TTL:
        return cached[1]
    prompt = (
        "You are a disciplined market-analysis assistant. Based ONLY on the supplied XAU/USD technical context, "
        "give a concise non-guaranteed trading analysis. Return JSON with keys: summary, bias, confidence, advice. "
        "Confidence must be an integer 0-100. Do not claim certainty or guaranteed profits.\n\n" + json.dumps(analysis_context, ensure_ascii=False)
    )
    if OPENAI_API_KEY:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=OPENAI_API_KEY)
            response = await client.responses.create(model=OPENAI_MODEL, input=prompt)
            text = getattr(response, "output_text", "").strip()
            if text:
                try:
                    parsed = json.loads(text)
                    result = {"mode": "openai", **parsed}
                    AI_CACHE[cache_key] = (now, result)
                    return result
                except json.JSONDecodeError:
                    result = {"mode": "openai", "summary": text, "bias": analysis_context.get("bias", "NEUTRAL"), "confidence": int(analysis_context.get("confidence", 50)), "advice": "Use the key levels and wait for candle confirmation."}
                    AI_CACHE[cache_key] = (now, result)
                    return result
        except Exception as exc:
            return {"mode": "fallback", "warning": f"AI provider unavailable: {exc}"}

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
        "bias": bias,
        "confidence": confidence,
        "advice": "Follow Pivot direction, wait for confirmed retest/breakout, and avoid entries around HIGH IMPACT news.",
    }
    AI_CACHE[cache_key] = (now, result)
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
    intervals=["1min","5min","15min","30min","1h","4h","1day"]
    async def one(tf: str):
        try:
            candles_data,mode,warning=await get_candles(symbol,tf,260)
            return tf, {**build_advanced_signal(candles_data,tf,news_blocked=news_blocked),"mode":mode,"warning":warning}
        except Exception as exc:
            return tf, {"interval":tf,"signal":"UNAVAILABLE","entry":None,"stop_loss":None,"take_profit":[],"confidence":0,"score":0,"setup":"ERROR","components":{},"reason":str(exc),"mode":"error","warning":str(exc)}
    pairs=await asyncio.gather(*(one(tf) for tf in intervals))
    items={tf:data for tf,data in pairs}
    return {"symbol":clean_symbol(symbol),"timeframes":items,"generated_at":datetime.now(timezone.utc).isoformat()}


async def build_full_analysis(symbol: str, interval: str) -> dict[str, Any]:
    symbol = clean_symbol(symbol)
    interval = validate_interval(interval)
    candles_data, mode, warning = await get_candles(symbol, interval, 160)
    current = candles_data[-1]["close"]
    previous_close = candles_data[-2]["close"] if len(candles_data) > 1 else current
    change_pct = ((current - previous_close) / previous_close * 100) if previous_close else 0
    reference, pivot_warning = await get_pivot_reference(symbol)
    levels = calculate_pivot_levels(reference["high"], reference["low"], reference["close"], current)
    calendar = await economic_calendar(2)
    blocked, news_reason = news_blackout(calendar.get("events", []))
    setup = build_key_level_signal(candles_data, levels, news_blocked=blocked)
    ta = technical_analysis(candles_data, levels, setup)
    mtf = await multi_timeframe(symbol)
    ai_context = {"bias": levels["bias"], "signal": setup["signal"], "setup": setup["setup"], "rsi": ta["rsi"], "mtf_overall": mtf["overall"], "levels": levels}
    ai = await ai_smart_analysis(ai_context)
    if setup["signal"] == "SELL":
        headline = f"SELL • Target {levels['s1']:.2f}"
    elif setup["signal"] == "BUY":
        headline = f"BUY • Target {levels['r1']:.2f}"
    else:
        headline = f"WAIT • {levels['bias']} bias"
    combined_warning = " | ".join(x for x in [warning, pivot_warning, calendar.get("warning"), news_reason] if x)
    return {
        "symbol": symbol, "current_price": round(current, 4), "change_pct": round(change_pct, 3),
        "headline": headline, "direction": setup["signal"], "bias": levels["bias"], "preference": setup["reason"],
        "setup": setup, "mode": mode, "warning": combined_warning or None, "interval": interval,
        "updated_at": datetime.now(timezone.utc).isoformat(), "levels": levels, "technical": ta,
        "multi_timeframe": mtf, "ai_smart": ai, "calendar": calendar, "candle": candle_countdown(interval),
    }


def settle_signal_row(row: SignalHistory, candles_data: list[dict[str, Any]]) -> bool:
    if row.outcome not in ("OPEN", "AMBIGUOUS") or row.direction not in ("BUY", "SELL"):
        return False
    try:
        payload = json.loads(row.payload)
        setup = payload.get("setup", {}) or payload.get("advanced", {})
        entry = float(setup.get("entry") or 0)
        sl = float(setup.get("stop_loss") or 0)
        tps = [float(x) for x in (setup.get("take_profit") or []) if x is not None]
    except (ValueError, TypeError, json.JSONDecodeError):
        return False
    if not entry or not sl or not tps:
        return False
    created = row.created_at.replace(tzinfo=timezone.utc) if row.created_at.tzinfo is None else row.created_at
    changed = False
    for c in candles_data:
        ts = datetime.fromtimestamp(c["time"], timezone.utc)
        if ts <= created:
            continue
        tp_hit = c["high"] >= tps[0] if row.direction == "BUY" else c["low"] <= tps[0]
        sl_hit = c["low"] <= sl if row.direction == "BUY" else c["high"] >= sl
        if tp_hit and sl_hit:
            row.outcome = "AMBIGUOUS"
            row.closed_at = ts
            changed = True
            break
        if tp_hit:
            row.outcome = "TP HIT"
            row.closed_at = ts
            changed = True
            break
        if sl_hit:
            row.outcome = "SL HIT"
            row.closed_at = ts
            changed = True
            break
    return changed


async def refresh_signal_outcomes(session: Session, user_id: int, limit: int = 100) -> list[SignalHistory]:
    rows = session.scalars(select(SignalHistory).where(SignalHistory.user_id == user_id).order_by(SignalHistory.created_at.asc())).all()
    grouped: dict[tuple[str, str], list[SignalHistory]] = {}
    for row in rows:
        if row.outcome in ("TP HIT", "SL HIT"):
            continue
        grouped.setdefault((row.symbol, row.interval), []).append(row)
    changed_any = False
    for (sym, tf), group in grouped.items():
        try:
            candles_data, _, _ = await get_candles(sym, tf, 500)
        except Exception:
            continue
        for row in group:
            changed_any = settle_signal_row(row, candles_data) or changed_any
    if changed_any:
        session.commit()
    return rows



class MarketStream:
    def __init__(self):
        self.clients={}; self.tasks={}; self.lock=asyncio.Lock()
    async def add(self,ws,symbol,interval):
        await ws.accept(); key=(clean_symbol(symbol),validate_interval(interval))
        async with self.lock:
            self.clients[ws]=key
            if key not in self.tasks or self.tasks[key].done(): self.tasks[key]=asyncio.create_task(self._run(key))
    async def remove(self,ws):
        async with self.lock:
            key=self.clients.pop(ws,None)
            if key and not any(v==key for v in self.clients.values()):
                t=self.tasks.pop(key,None)
                if t and not t.done(): t.cancel()
    async def broadcast(self,key,message):
        dead=[]
        async with self.lock: items=[ws for ws,k in self.clients.items() if k==key]
        for ws in items:
            try: await ws.send_json(message)
            except Exception: dead.append(ws)
        for ws in dead: await self.remove(ws)
    async def _run(self,key):
        symbol,interval=key; backoff=1
        while True:
            provider=live_provider()
            try:
                import websockets
                if provider=="realmarketapi":
                    tf=realmarket_timeframe(interval)
                    url=f"wss://api.realmarketapi.com/price?apiKey={REALMARKET_API_KEY}&symbolCode={realmarket_symbol(symbol)}&timeFrame={tf}"
                    async with websockets.connect(url,ping_interval=15,ping_timeout=20,close_timeout=5) as ws:
                        backoff=1; await self.broadcast(key,{"type":"status","status":"connected","provider":"realmarketapi","interval":interval})
                        while True:
                            msg=json.loads(await ws.recv())
                            if isinstance(msg,dict):
                                try:
                                    c=_rm_candle(msg); await self.broadcast(key,{"type":"candle","symbol":symbol,"interval":interval,"candle":c,"price":c["close"],"timestamp":c["time"],"source":"realmarketapi"})
                                except Exception:
                                    price=msg.get("price") or msg.get("Price") or msg.get("ClosePrice")
                                    if price is not None: await self.broadcast(key,{"type":"tick","symbol":symbol,"price":float(price),"timestamp":int(float(msg.get("timestamp") or datetime.now(timezone.utc).timestamp())),"source":"realmarketapi"})
                elif provider=="twelvedata":
                    url=f"wss://ws.twelvedata.com/v1/quotes/price?apikey={TWELVE_DATA_API_KEY}"
                    async with websockets.connect(url,ping_interval=10,ping_timeout=20,close_timeout=5) as ws:
                        await ws.send(json.dumps({"action":"subscribe","params":{"symbols":symbol}})); backoff=1
                        await self.broadcast(key,{"type":"status","status":"connected","provider":"twelvedata","interval":interval})
                        while True:
                            msg=json.loads(await ws.recv())
                            if msg.get("event")=="price": await self.broadcast(key,{"type":"tick","symbol":symbol,"price":float(msg["price"]),"timestamp":int(float(msg.get("timestamp") or datetime.now(timezone.utc).timestamp())),"source":"twelvedata"})
                else:
                    await self.broadcast(key,{"type":"error","code":"LIVE_NOT_CONFIGURED","message":"Set REALMARKET_API_KEY or TWELVE_DATA_API_KEY."}); return
            except asyncio.CancelledError: raise
            except Exception as exc:
                await self.broadcast(key,{"type":"reconnecting","message":str(exc),"retry_in":backoff}); await asyncio.sleep(backoff); backoff=min(backoff*2,30)

market_stream = MarketStream()

@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"status":"ok","provider":live_provider() or MARKET_PROVIDER,"realmarket_configured":bool(REALMARKET_API_KEY),"twelvedata_configured":False,"market_api_configured":bool(live_provider()),"calendar_configured":bool(FINNHUB_API_KEY),"ai_configured":bool(OPENAI_API_KEY),"database":DATABASE_URL.split(":",1)[0],"realtime_stream":bool(live_provider()),"allow_demo":ALLOW_DEMO,"timestamp":datetime.now(timezone.utc).isoformat()}

@app.get("/api/market/diagnostics")
async def market_diagnostics() -> dict[str, Any]:
    result={"symbol":DEFAULT_SYMBOL,"providers":{},"timestamp":datetime.now(timezone.utc).isoformat()}
    for name, configured in (("realmarketapi", REALMARKET_API_KEY),("twelvedata",TWELVE_DATA_API_KEY)):
        item={"configured":bool(configured),"ok":False}
        if configured:
            try:
                if name=="realmarketapi":
                    item["price"]=await fetch_realmarket_price(DEFAULT_SYMBOL)
                else:
                    item["price"]=await fetch_twelvedata_price(clean_symbol(DEFAULT_SYMBOL))
                item["ok"]=True
            except Exception as exc:
                item["error"]=f"{type(exc).__name__}: {exc}"
        result["providers"][name]=item
    result["live_ready"]=any(x.get("ok") for x in result["providers"].values())
    return result


@app.get("/api/email/smtp-status")
async def smtp_status() -> dict[str, Any]:
    return {
        "configured": smtp_configured(),
        "host": SMTP_HOST,
        "port": SMTP_PORT,
        "user_present": bool(SMTP_USER),
        "from_present": bool(SMTP_FROM),
        "password_present": bool(SMTP_PASSWORD),
        "starttls": SMTP_USE_STARTTLS and not (SMTP_USE_SSL or SMTP_PORT == 465),
        "ssl": SMTP_USE_SSL or SMTP_PORT == 465,
        "require_delivery": REQUIRE_EMAIL_DELIVERY,
        "note": "Gmail SMTP 535/534 auth errors normally mean App Password/2-Step Verification or account credentials are incorrect." if SMTP_HOST == "smtp.gmail.com" else "Check SMTP credentials and provider security settings.",
    }


@app.post("/api/auth/register")
async def register(body: RegisterBody, session: Session = Depends(db)) -> dict[str, Any]:
    email = body.email.strip().lower()
    if not valid_email(email):
        raise HTTPException(status_code=400, detail="To'g'ri elektron pochta manzilini kiriting, masalan: user@gmail.com")
    if session.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Bu elektron pochta allaqachon ro'yxatdan o'tgan")

    login_name, generated_password = generate_credentials()
    while session.scalar(select(User).where(User.username == login_name)):
        login_name, generated_password = generate_credentials()

    # Generate a unique login/password for every email address.
    # The normalized email address is unique and is never reused.
    emailed, email_status = send_credentials_email(email, login_name, generated_password)
    if REQUIRE_EMAIL_DELIVERY and not emailed:
        raise HTTPException(status_code=503, detail=email_status + " Hisob yaratilmaydi; SMTP sozlamalarini tekshiring.")

    user = User(email=email, username=login_name, password_hash=hash_password(generated_password))
    user.subscription = Subscription(plan="free", status="active", renews_at=None)
    session.add(user)
    session.commit()
    session.refresh(user)

    result = {
        "token": create_session(user.id, session),
        "user": {"id": user.id, "login": login_name, "email": email, "plan": "free"},
        "email_sent": emailed,
        "email_message": email_status,
        "credentials_delivery": "email" if emailed else "local_fallback",
    }
    # Only expose credentials when SMTP delivery did not succeed (development fallback).
    if not emailed:
        result["credentials"] = {"login": login_name, "password": generated_password}
    return result


@app.post("/api/auth/login")
async def login(body: AuthBody, session: Session = Depends(db)) -> dict[str, Any]:
    identity = body.username.strip()
    if not identity or not body.password:
        raise HTTPException(status_code=400, detail="Login va parolni kiriting")
    if "@" in identity:
        user = session.scalar(select(User).where(User.email == identity.lower()))
    else:
        user = session.scalar(select(User).where(User.username == identity))
        if user is None:
            user = session.scalar(select(User).where(User.email == identity))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Login yoki parol noto'g'ri")
    plan = user.subscription.plan if user.subscription else "free"
    return {"token": create_session(user.id, session), "user": {"id": user.id, "login": user.username or user.email, "email": user.email, "plan": plan}}


@app.post("/api/auth/logout")
async def logout(authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, str]:
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization.split(" ", 1)[1].strip()
        row = session.scalar(select(SessionToken).where(SessionToken.token_hash == token_hash(raw)))
        if row:
            session.delete(row); session.commit()
    return {"status": "ok"}



@app.get("/api/auth/me")
async def auth_me(authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    user = current_user(authorization, session)
    plan = user.subscription.plan if user.subscription else "free"
    return {"user":{"id":user.id,"login":user.username or user.email,"email":user.email,"plan":plan},"plan":plan}


@app.websocket("/api/v1/ws/market/{symbol:path}")
async def market_websocket(ws: WebSocket, symbol: str, interval: str = Query(DEFAULT_INTERVAL)) -> None:
    normalized=clean_symbol(symbol)
    if not REALMARKET_API_KEY:
        await ws.accept(); await ws.send_json({"type":"error","code":"LIVE_NOT_CONFIGURED","message":"LIVE market stream requires REALMARKET_API_KEY."}); await ws.close(code=1013); return
    await market_stream.add(ws,normalized,interval)
    try:
        await ws.send_json({"type":"status","status":"connecting","symbol":normalized,"interval":validate_interval(interval)})
        while True: await ws.receive_text()
    except WebSocketDisconnect: pass
    except Exception: pass
    finally: await market_stream.remove(ws)


@app.get("/api/v1/candles/{symbol:path}")
async def candles(symbol: str, interval: str = Query(DEFAULT_INTERVAL), limit: int = Query(CANDLE_LIMIT, ge=50, le=500)) -> dict[str, Any]:
    interval = validate_interval(interval)
    symbol = clean_symbol(symbol)
    try:
        data, mode, provider_name = await get_chart_history(symbol, interval, 31)
        warning = provider_name if mode == "live" else provider_name
        return {"symbol":symbol,"interval":interval,"mode":mode,"warning":warning,"count":len(data),"candles":data,"candle":candle_countdown(interval),"history_days":31 if mode=="live" else None,"provider":provider_name}
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"symbol": symbol, "interval": interval, "mode": mode, "warning": warning, "count": len(data), "candles": data, "candle": candle_countdown(interval), "history_days": None}


@app.get("/api/v1/quote/{symbol:path}")
async def quote(symbol: str) -> dict[str, Any]:
    symbol = clean_symbol(symbol); errors=[]
    try:
        node_url=f"{NODE_MARKET_URL}/market/price?symbol={urlquote(symbol)}"
        async with httpx.AsyncClient(timeout=NODE_QUOTE_TIMEOUT) as client:
            r=await client.get(node_url); data=r.json() if r.content else {}
        if r.is_success and isinstance(data,dict) and data.get("price") is not None:
            return {"symbol":symbol,"price":to_float(data["price"]),"mode":"live","provider":data.get("provider","node-market-gateway"),"timestamp":datetime.now(timezone.utc).isoformat()}
        errors.append(f"node: {data.get('error','no live cached quote') if isinstance(data,dict) else 'invalid response'}")
    except Exception as exc: errors.append(f"node: {type(exc).__name__}: {exc}")
    if live_provider() == "yahoo":
        try:
            price = await fetch_yahoo_price(symbol)
            return {"symbol":symbol,"price":price,"mode":"live","provider":"yahoo-gold","timestamp":datetime.now(timezone.utc).isoformat()}
        except MarketDataError as exc:
            errors.append(f"yahoo: {exc}")
    try:
        price=await fetch_realmarket_price(symbol)
        return {"symbol":symbol,"price":price,"mode":"live","provider":"realmarketapi","timestamp":datetime.now(timezone.utc).isoformat()}
    except MarketDataError as exc: errors.append(f"realmarketapi: {exc}")
    raise HTTPException(status_code=503, detail="No live quote available. " + " | ".join(errors))


@app.get("/api/v1/market/snapshot/{symbol:path}")
async def market_snapshot(symbol: str, interval: str = Query(DEFAULT_INTERVAL), limit: int = Query(160, ge=50, le=500)) -> dict[str, Any]:
    """Single canonical market snapshot: the same RealMarketAPI candles feed chart metadata and analysis consumers."""
    interval = validate_interval(interval); symbol = clean_symbol(symbol)
    candles_data, mode, warning = await get_candles(symbol, interval, limit)
    analysis = await build_full_analysis(symbol, interval)
    return {"symbol":symbol,"interval":interval,"mode":mode,"provider":live_provider() or "market","warning":warning,"candles":candles_data,"analysis":analysis,"generated_at":datetime.now(timezone.utc).isoformat()}


@app.get("/api/v1/analysis/{symbol:path}")
async def get_symbol_analysis(symbol: str, interval: str = Query(DEFAULT_INTERVAL)) -> dict[str, Any]:
    try:
        return await build_full_analysis(symbol, interval)
    except MarketDataError as exc:
        return {"ok":False,"mode":"live","provider":"RealMarketAPI","error":str(exc),"symbol":clean_symbol(symbol),"interval":validate_interval(interval)}


@app.get("/api/v1/multi-timeframe/{symbol:path}")
async def get_mtf(symbol: str) -> dict[str, Any]:
    return await multi_timeframe(clean_symbol(symbol))


@app.get("/api/v1/sessions")
async def get_sessions() -> dict[str, Any]:
    return await market_sessions()


@app.get("/api/v1/calendar")
async def get_calendar(days: int = Query(2, ge=1, le=7)) -> dict[str, Any]:
    return await economic_calendar(days)


@app.get("/api/v1/candle-countdown")
async def get_countdown(interval: str = Query(DEFAULT_INTERVAL)) -> dict[str, Any]:
    return candle_countdown(interval)


@app.get("/api/v1/signals/advanced/{symbol:path}")
async def advanced_signals(symbol: str, authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    user = current_user(authorization, session)
    # Economic calendar blackout is applied globally to all timeframes.
    cal = await economic_calendar(1)
    blocked = any(e.get("impact") == "HIGH" for e in cal.get("events", [])[:50]) and False
    # Calendar endpoint may not provide an explicit active window; keep signal generation usable and expose calendar separately.
    return await build_advanced_signals(clean_symbol(symbol), news_blocked=blocked)


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
        items.append({"id": r.id, "symbol": r.symbol, "interval": r.interval, "direction": r.direction, "entry": setup.get("entry"), "tp": setup.get("take_profit", []), "sl": setup.get("stop_loss"), "headline": r.headline, "price": r.price, "outcome": r.outcome, "created_at": r.created_at.isoformat(), "closed_at": r.closed_at.isoformat() if r.closed_at else None})
    return {"items": items}


@app.get("/")
async def read_root() -> FileResponse:
    return FileResponse(os.path.join(BASE_DIR, "index.html"))
