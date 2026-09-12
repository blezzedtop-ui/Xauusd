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
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, create_engine, select, func
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
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-sol").strip() or "gpt-5.6-sol"
HF_TOKEN = (os.getenv("HF_TOKEN", "").strip() or os.getenv("HUGGINGFACE_API_KEY", "").strip())
HF_MODEL = os.getenv("HF_MODEL", "openai/gpt-oss-120b:fastest").strip() or "openai/gpt-oss-120b:fastest"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip() or "openai/gpt-oss-120b"
GROQ_QWEN_MODEL = os.getenv("GROQ_QWEN_MODEL", "qwen/qwen3.6-27b").strip() or "qwen/qwen3.6-27b"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip() or "gemini-3.8-flash"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free").strip() or "openrouter/free"
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "").strip()
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest").strip() or "mistral-small-latest"
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "").strip()
CEREBRAS_MODEL = os.getenv("CEREBRAS_MODEL", "qwen-3.8-27b").strip() or "qwen-3.8-27b"
if CEREBRAS_MODEL in {"llama-3.3-70b", "llama-3.3-70b-versatile", "gpt-oss-120b"}:
    CEREBRAS_MODEL = "qwen-3.8-27b"
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
CLOUDFLARE_API_TOKEN = (os.getenv("CLOUDFLARE_API_TOKEN", "").strip() or os.getenv("CLOUDFLARE_API_KEY", "").strip())
CLOUDFLARE_MODEL = os.getenv("CLOUDFLARE_MODEL", "@cf/meta/llama-3.1-8b-instruct").strip() or "@cf/meta/llama-3.1-8b-instruct"
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash").strip() or "deepseek-flash"
if DEEPSEEK_MODEL == "deepseek-v4-flash":
    DEEPSEEK_MODEL = "deepseek-flash"
AI_PROVIDER = os.getenv("AI_PROVIDER", "auto").strip().lower() or "auto"
AI_FALLBACK_ORDER = [x.strip().lower() for x in os.getenv("AI_FALLBACK_ORDER", "groq,deepseek,gemini,groq_qwen,openai,mistral,cerebras,cloudflare,huggingface,openrouter").split(",") if x.strip()]
AI_ROUTER_MODE = os.getenv("AI_ROUTER_MODE", "score").strip().lower() or "score"
# Provider profile: quality, speed, capacity/limits, cost-efficiency (0-100).
# These are routing heuristics, not provider guarantees; live status is weighted dynamically.
AI_PROVIDER_PROFILE = {
    "groq": {"quality": 95, "speed": 99, "capacity": 78, "cost": 94},
    "deepseek": {"quality": 96, "speed": 88, "capacity": 99, "cost": 97},
    "gemini": {"quality": 94, "speed": 91, "capacity": 88, "cost": 88},
    "groq_qwen": {"quality": 86, "speed": 98, "capacity": 78, "cost": 94},
    "openai": {"quality": 97, "speed": 82, "capacity": 70, "cost": 62},
    "mistral": {"quality": 84, "speed": 89, "capacity": 78, "cost": 88},
    "cerebras": {"quality": 88, "speed": 100, "capacity": 82, "cost": 90},
    "cloudflare": {"quality": 73, "speed": 86, "capacity": 84, "cost": 95},
    "openrouter": {"quality": 76, "speed": 78, "capacity": 68, "cost": 100},
    "huggingface": {"quality": 91, "speed": 86, "capacity": 90, "cost": 95},
}
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
AI_CACHE_TTL = int(os.getenv("AI_CACHE_TTL", "86400"))
# Cache AI results for the entire candle lifetime; candle_time is part of every key.
# This prevents repeated requests on the same candle and greatly reduces quota use.
AI_RATE_LIMIT_RETRY_NEXT_CANDLE = True
AI_PROVIDER_COOLDOWN_SECONDS = int(os.getenv("AI_PROVIDER_COOLDOWN_SECONDS", "120"))
AI_PROVIDER_COOLDOWN_UNTIL: dict[str, float] = {}

AI_PROVIDER_STATUS: dict[str, dict[str, Any]] = {}
# Runtime AI controls. OFF providers are never called by the router.
AI_PROVIDER_ENABLED: dict[str, bool] = {
    "groq": True, "deepseek": True, "gemini": True, "groq_qwen": True,
    "openai": True, "mistral": True, "cerebras": True, "cloudflare": True,
    "huggingface": True, "openrouter": True,
}
AI_AUTO_MODE = True
AI_SIGNAL_CONFIRM_ONLY = os.getenv("AI_SIGNAL_CONFIRM_ONLY", "true").lower() == "true"

def _provider_error_details(exc: Exception) -> tuple[str, int | None]:
    """Return a compact, user-safe provider error and HTTP status when available."""
    status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            msg = err.get("message") or err.get("type") or err.get("code")
        else:
            msg = body.get("message") or body.get("detail")
    else:
        msg = None
    raw = str(msg or exc).strip().replace("\n", " ")
    low = raw.lower()
    if "rate limit" in low or "too many requests" in low or "quota" in low:
        category = "rate limit / quota"
    elif status in (401, 403) or "invalid api key" in low or "unauthorized" in low or "forbidden" in low:
        category = "authentication / permission"
    elif status == 404 or "not found" in low or "model" in low and "found" in low:
        category = "model / endpoint"
    elif "timeout" in low or "timed out" in low:
        category = "timeout / network"
    elif "connection" in low or "dns" in low:
        category = "network / connection"
    else:
        category = "provider error"
    prefix = f"HTTP {status} · {category}" if status else category
    return f"{prefix} · {raw[:280]}", status

async def _openai_compatible_completion(api_key: str, base_url: str, model: str, prompt: str, provider: str, extra_headers: dict[str, str] | None = None) -> tuple[str, str]:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=REQUEST_TIMEOUT, max_retries=0, default_headers=extra_headers or None)
    kwargs = dict(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    # Some compatible providers/models reject response_format=json_object.
    # Try structured output first, then transparently retry once without it.
    try:
        response = await client.chat.completions.create(**kwargs, response_format={"type": "json_object"})
    except Exception as first_exc:
        msg = str(first_exc).lower()
        if any(x in msg for x in ("response_format", "json_object", "unsupported", "not support")):
            response = await client.chat.completions.create(**kwargs)
        else:
            raise
    text = (response.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError(f"{provider}: empty response")
    return text, provider

async def _cloudflare_completion(prompt: str) -> tuple[str, str]:
    url=f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run/{CLOUDFLARE_MODEL}"
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        r=await client.post(url, headers={"Authorization":f"Bearer {CLOUDFLARE_API_TOKEN}","Content-Type":"application/json"}, json={"prompt":prompt})
        r.raise_for_status()
        data=r.json()
    text=((data.get("result") or {}).get("response") or "").strip()
    if not text:
        raise RuntimeError("cloudflare: empty response")
    return text, "cloudflare"

async def _provider_call(provider: str, prompt: str) -> tuple[str, str]:
    if provider == "groq" and GROQ_API_KEY:
        return await _openai_compatible_completion(GROQ_API_KEY, "https://api.groq.com/openai/v1", GROQ_MODEL, prompt, "groq")
    if provider == "groq_qwen" and GROQ_API_KEY:
        return await _openai_compatible_completion(GROQ_API_KEY, "https://api.groq.com/openai/v1", GROQ_QWEN_MODEL, prompt, "groq_qwen")
    if provider == "gemini" and GEMINI_API_KEY:
        # Use Gemini's native GenerateContent API rather than the compatibility
        # layer so API-key authentication and model errors are reported directly.
        url=f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
        payload={
            "contents":[{"role":"user","parts":[{"text":prompt}]}],
            "generationConfig":{"temperature":0.1,"responseMimeType":"application/json"}
        }
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            r=await client.post(url, headers={"x-goog-api-key":GEMINI_API_KEY,"Content-Type":"application/json"}, json=payload)
            if r.status_code >= 400:
                # Raise a typed error with Google's response body so the status panel
                # can distinguish invalid key, permission, quota and model errors.
                try:
                    detail=r.json()
                except Exception:
                    detail=r.text
                exc=RuntimeError(f"Gemini HTTP {r.status_code}: {detail}")
                setattr(exc,"status_code",r.status_code)
                setattr(exc,"body",detail if isinstance(detail,dict) else {"message":str(detail)})
                raise exc
            data=r.json()
        candidates=data.get("candidates") or []
        parts=((candidates[0].get("content") or {}).get("parts") or []) if candidates else []
        text="".join(str(x.get("text", "")) for x in parts).strip()
        if not text:
            raise RuntimeError("gemini: empty response")
        return text, "gemini"
    if provider == "openrouter" and OPENROUTER_API_KEY:
        return await _openai_compatible_completion(OPENROUTER_API_KEY, "https://openrouter.ai/api/v1", OPENROUTER_MODEL, prompt, "openrouter", {"HTTP-Referer": APP_BASE_URL, "X-OpenRouter-Title": APP_TITLE})
    if provider == "mistral" and MISTRAL_API_KEY:
        return await _openai_compatible_completion(MISTRAL_API_KEY, "https://api.mistral.ai/v1", MISTRAL_MODEL, prompt, "mistral")
    if provider == "cerebras" and CEREBRAS_API_KEY:
        return await _openai_compatible_completion(CEREBRAS_API_KEY, "https://api.cerebras.ai/v1", CEREBRAS_MODEL, prompt, "cerebras", {"X-Cerebras-Version-Patch":"2"})
    if provider == "cloudflare" and CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN:
        return await _cloudflare_completion(prompt)
    if provider == "deepseek" and DEEPSEEK_API_KEY:
        return await _openai_compatible_completion(DEEPSEEK_API_KEY, "https://api.deepseek.com", DEEPSEEK_MODEL, prompt, "deepseek")
    if provider == "huggingface" and HF_TOKEN:
        return await _openai_compatible_completion(HF_TOKEN, "https://router.huggingface.co/v1", HF_MODEL, prompt, "huggingface")
    if provider == "openai" and OPENAI_API_KEY:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=REQUEST_TIMEOUT, max_retries=0)
        response = await client.responses.create(model=OPENAI_MODEL, input=prompt)
        text = getattr(response, "output_text", "").strip()
        if text:
            return text, "openai"
    raise RuntimeError(f"{provider}: not configured")

async def ai_json_completion(prompt: str) -> tuple[str, str]:
    """Free-first AI router with automatic provider failover.

    TradingView/quant data is supplied by the caller; this router never fetches
    market data. A provider error, timeout or rate limit immediately advances
    to the next configured provider. The deterministic engine remains the final fallback.
    """
    configured={
        "groq": bool(GROQ_API_KEY),
        "gemini": bool(GEMINI_API_KEY),
        "openrouter": bool(OPENROUTER_API_KEY),
        "groq_qwen": bool(GROQ_API_KEY),
        "mistral": bool(MISTRAL_API_KEY),
        "cerebras": bool(CEREBRAS_API_KEY),
        "cloudflare": bool(CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN),
        "deepseek": bool(DEEPSEEK_API_KEY),
        "openai": bool(OPENAI_API_KEY),
        "huggingface": bool(HF_TOKEN),
    }
    raw_order = [AI_PROVIDER] if AI_PROVIDER not in {"auto", ""} else AI_FALLBACK_ORDER
    # Never call or mark a provider that has no credentials configured.
    candidates = [p for p in raw_order if configured.get(p, False) and AI_PROVIDER_ENABLED.get(p, True)]
    errors=[]
    now_mono = asyncio.get_running_loop().time()

    def route_score(provider: str) -> float:
        prof = AI_PROVIDER_PROFILE.get(provider, {"quality":70,"speed":70,"capacity":60,"cost":60})
        base = (prof["quality"]*0.40 + prof["speed"]*0.20 + prof["capacity"]*0.25 + prof["cost"]*0.15)
        st = AI_PROVIDER_STATUS.get(provider) or {}
        status = st.get("status")
        if status == "ONLINE": base += 8
        elif status == "LIMITED": base -= 18
        if AI_PROVIDER_COOLDOWN_UNTIL.get(provider, 0.0) > now_mono: base -= 35
        return round(base, 2)

    # In AUTO mode choose the best currently healthy provider by a weighted
    # quality/speed/capacity/cost score. If it fails, immediately fall through
    # the remaining providers in descending score order.
    order = sorted(candidates, key=route_score, reverse=True) if AI_ROUTER_MODE == "score" else candidates
    for provider in order:
        # Skip a provider briefly after a rate-limit response instead of hammering it.
        cooldown_until = AI_PROVIDER_COOLDOWN_UNTIL.get(provider, 0.0)
        if cooldown_until > now_mono:
            AI_PROVIDER_STATUS[provider] = {"status":"LIMITED", "checked_at":datetime.now(timezone.utc).isoformat(),
                                            "error":f"rate-limit cooldown ({int(cooldown_until-now_mono)}s remaining)"}
            errors.append(f"{provider}: cooldown")
            continue
        try:
            text, used = await _provider_call(provider, prompt)
            AI_PROVIDER_STATUS[used] = {"status":"ONLINE", "checked_at":datetime.now(timezone.utc).isoformat(), "error":""}
            AI_PROVIDER_COOLDOWN_UNTIL.pop(used, None)
            return text, used
        except Exception as exc:
            msg, http_status = _provider_error_details(exc)
            low=msg.lower()
            limited = http_status == 429 or "rate limit" in low or "rate_limit" in low or "quota" in low or "too many requests" in low
            if limited:
                AI_PROVIDER_COOLDOWN_UNTIL[provider] = now_mono + AI_PROVIDER_COOLDOWN_SECONDS
            AI_PROVIDER_STATUS[provider] = {"status":"LIMITED" if limited else "OFFLINE", "checked_at":datetime.now(timezone.utc).isoformat(), "error":msg[:360], "http_status":http_status}
            errors.append(f"{provider}: {msg[:180]}")
            continue
    raise RuntimeError("All configured AI providers failed: " + " | ".join(errors))

# Book/OpenAI second-opinion cache: one OpenAI call per newly closed/current candle.
BOOK_OPENAI_CACHE_TTL = int(os.getenv("BOOK_OPENAI_CACHE_TTL", "86400"))
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
MT5_BRIDGE_TOKEN = os.getenv("MT5_BRIDGE_TOKEN", "change-this-mt5-bridge-token").strip()
MT5_AUTO_TRADING = os.getenv("MT5_AUTO_TRADING", "false").lower() == "true"
MT5_LOT_SIZE = float(os.getenv("MT5_DEFAULT_LOT", "0.01"))
MT5_BRIDGE_STATE: dict[str, Any] = {"connected": False, "account": None, "server": None, "balance": None, "equity": None, "free_margin": None, "margin": None, "positions": 0, "last_seen": None, "last_error": "", "symbol": None, "candles": {}, "markets": {}}
MT5_ORDER_QUEUE: list[dict[str, Any]] = []
MT5_ORDER_ATTEMPTS: dict[str, int] = {}
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
    source: Mapped[str] = mapped_column(String(40), default="Signals", index=True)
    candle_time: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)


Base.metadata.create_all(engine)

HISTORY_LOCAL_TZ = ZoneInfo("Asia/Tashkent")

def history_period_bounds(period: str | None) -> tuple[datetime | None, datetime | None]:
    """Return UTC-aware [start, end) bounds for user-facing history filters.
    period: all | day | month. Boundaries are based on Asia/Tashkent local time.
    """
    p = (period or "all").strip().lower()
    if p in {"", "all", "none"}:
        return None, None
    now_local = datetime.now(HISTORY_LOCAL_TZ)
    if p in {"day", "daily", "today"}:
        start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local + timedelta(days=1)
    elif p in {"month", "monthly", "this_month"}:
        start_local = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start_local.month == 12:
            end_local = start_local.replace(year=start_local.year + 1, month=1)
        else:
            end_local = start_local.replace(month=start_local.month + 1)
    else:
        raise HTTPException(status_code=400, detail="period faqat all, day yoki month bo‘lishi mumkin")
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)

def filter_history_rows(rows: list[SignalHistory], period: str | None, exact_date: str | None = None) -> list[SignalHistory]:
    if exact_date:
        try:
            d = datetime.strptime(exact_date, "%Y-%m-%d").date()
        except ValueError:
            return []
        out=[]
        tz=ZoneInfo("Asia/Tashkent")
        for r in rows:
            dt=r.created_at
            if dt is None: continue
            if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
            local=dt.astimezone(tz)
            if local.date()==d: out.append(r)
        return out
    start, end = history_period_bounds(period)
    if start is None: return rows
    out=[]
    for r in rows:
        dt = r.created_at
        if dt is None: continue
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        else: dt = dt.astimezone(timezone.utc)
        if start <= dt < end: out.append(r)
    return out

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
            sig_cols = {c["name"] for c in inspector.get_columns("signal_history")}
            if "source" not in sig_cols:
                conn.exec_driver_sql("ALTER TABLE signal_history ADD COLUMN source VARCHAR(40) DEFAULT 'Signals'")
            if "candle_time" not in sig_cols:
                conn.exec_driver_sql("ALTER TABLE signal_history ADD COLUMN candle_time VARCHAR(40)")
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
AUTO_ENTRY_THRESHOLD = 84.99
AUTO_ENTRY_DUPLICATE_MINUTES = int(os.getenv("AUTO_ENTRY_DUPLICATE_MINUTES", "5"))
AUTO_ENTRY_MIN_ZONE = float(os.getenv("AUTO_ENTRY_MIN_ZONE", "88"))
AUTO_ENTRY_MIN_AI_AGREEMENT = float(os.getenv("AUTO_ENTRY_MIN_AI_AGREEMENT", "75"))
AUTO_ENTRY_REQUIRE_MTF = os.getenv("AUTO_ENTRY_REQUIRE_MTF", "true").lower() == "true"


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


async def fetch_tradingview_candles(symbol: str, interval: str, limit: int = TRADINGVIEW_BARS) -> list[dict[str, Any]]:
    """Shared TradingView/OANDA cache with single-flight locking and one retry."""
    symbol = clean_symbol(symbol)
    interval = validate_interval(interval)
    key = (symbol, interval)
    now = asyncio.get_running_loop().time()
    cached = TV_CANDLE_CACHE.get(key)
    if cached and cached[1] and now - cached[0] < TRADINGVIEW_CACHE_TTL:
        return cached[1][-limit:]
    async with TV_CANDLE_LOCKS_GUARD:
        lock = TV_CANDLE_LOCKS.setdefault(key, asyncio.Lock())
    async with lock:
        now = asyncio.get_running_loop().time()
        cached = TV_CANDLE_CACHE.get(key)
        if cached and cached[1] and now - cached[0] < TRADINGVIEW_CACHE_TTL:
            return cached[1][-limit:]
        last_exc = None
        bars = []
        for attempt in range(2):
            try:
                bars = await _fetch_tradingview_candles_once(symbol, interval, max(limit, 80))
                if bars:
                    break
            except Exception as exc:
                last_exc = exc
                if attempt == 0:
                    await asyncio.sleep(0.25)
        if not bars:
            stale = TV_CANDLE_CACHE.get(key)
            if stale and stale[1]:
                return stale[1][-limit:]
            if last_exc:
                raise last_exc
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




def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    k = 2.0 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e

def _classic_trade(candles: list[dict[str, Any]], levels: dict[str, Any]) -> dict[str, Any]:
    closes = [float(c["close"]) for c in candles]
    # Base the Classic decision on the last COMPLETED candle; the newest candle may still be forming.
    cur = candles[-2]; prev = candles[-3]
    price = closes[-1]
    r = rsi(candles); a = atr(candles)
    ema20 = _ema(closes[-80:], 20); ema50 = _ema(closes[-120:], 50)
    macd_line = _ema(closes[-120:], 12) - _ema(closes[-120:], 26)
    macd_prev = _ema(closes[-121:-1], 12) - _ema(closes[-121:-1], 26) if len(closes) > 121 else macd_line
    macd_state = "BULLISH" if macd_line > macd_prev else "BEARISH"
    body = abs(float(cur["close"])-float(cur["open"]))
    rng = max(float(cur["high"])-float(cur["low"]), 1e-9)
    bullish_candle = float(cur["close"]) > float(cur["open"]) and body/rng >= 0.45
    bearish_candle = float(cur["close"]) < float(cur["open"]) and body/rng >= 0.45
    prev_body = abs(float(prev["close"])-float(prev["open"]))
    bullish_engulf = bullish_candle and float(prev["close"]) < float(prev["open"]) and float(cur["open"]) <= float(prev["close"]) and float(cur["close"]) >= float(prev["open"])
    bearish_engulf = bearish_candle and float(prev["close"]) > float(prev["open"]) and float(cur["open"]) >= float(prev["close"]) and float(cur["close"]) <= float(prev["open"])
    pattern = "BULLISH ENGULFING" if bullish_engulf else "BEARISH ENGULFING" if bearish_engulf else "BULLISH CANDLE" if bullish_candle else "BEARISH CANDLE" if bearish_candle else "NEUTRAL CANDLE"
    score = 0; reasons=[]
    trend = "BULLISH" if ema20 > ema50 and price > ema20 else "BEARISH" if ema20 < ema50 and price < ema20 else "MIXED"
    if trend == "BULLISH": score += 2; reasons.append("EMA20 > EMA50 / price above EMA20")
    elif trend == "BEARISH": score -= 2; reasons.append("EMA20 < EMA50 / price below EMA20")
    if price >= levels["pivot"]: score += 1; reasons.append("price above Pivot")
    else: score -= 1; reasons.append("price below Pivot")
    if r >= 55 and r < 70: score += 1; reasons.append("RSI bullish zone")
    elif r <= 45 and r > 30: score -= 1; reasons.append("RSI bearish zone")
    if macd_state == "BULLISH": score += 1; reasons.append("MACD bullish")
    else: score -= 1; reasons.append("MACD bearish")
    if bullish_engulf: score += 2; reasons.append("bullish engulfing")
    elif bearish_engulf: score -= 2; reasons.append("bearish engulfing")
    # Classic S/R context: reward rejection near a level, but avoid chasing extended moves.
    near_r1 = abs(price-levels["r1"]) <= max(a*0.35, 0.5)
    near_s1 = abs(price-levels["s1"]) <= max(a*0.35, 0.5)
    if near_s1 and bullish_candle: score += 2; reasons.append("support rejection")
    if near_r1 and bearish_candle: score -= 2; reasons.append("resistance rejection")
    zone=_snr_zone_analysis(candles)
    near_strong_support=zone["support"]["strength"]>=82 and zone["support"]["distance_pct"]<=0.75
    near_strong_resistance=zone["resistance"]["strength"]>=82 and zone["resistance"]["distance_pct"]<=0.75
    if near_strong_support and bullish_candle: score += 2; reasons.append("strong support zone")
    if near_strong_resistance and bearish_candle: score -= 2; reasons.append("strong resistance zone")
    direction = "BUY" if score >= 4 else "SELL" if score <= -4 else "WAIT"
    # Classic entries are only permitted from a strong zone, never in the middle of a range.
    if direction=="BUY" and not near_strong_support: direction="WAIT"; reasons.append("no strong entry zone")
    if direction=="SELL" and not near_strong_resistance: direction="WAIT"; reasons.append("no strong entry zone")
    confidence = min(97, 50 + abs(score)*7 + (5 if (near_strong_support or near_strong_resistance) else 0))
    entry = round(price, 2)
    if direction == "BUY":
        sl = round(min(float(cur["low"]), levels["s1"]) - max(a*0.15, 0.1), 2)
        tp = [round(levels["r1"],2), round(levels["r2"],2)]
    elif direction == "SELL":
        sl = round(max(float(cur["high"]), levels["r1"]) + max(a*0.15, 0.1), 2)
        tp = [round(levels["s1"],2), round(levels["s2"],2)]
    else: sl=None; tp=[]
    return {"signal":direction,"confidence":confidence,"score":score,"entry":entry,"stop_loss":sl,"take_profit":tp,
            "trend":trend,"rsi":round(r,2),"rsi_state":"OVERBOUGHT" if r>=70 else "OVERSOLD" if r<=30 else "NEUTRAL",
            "ema20":round(ema20,2),"ema50":round(ema50,2),"macd":round(macd_line,5),"macd_state":macd_state,
            "pattern":pattern,"pivot":levels["pivot"],"support":[levels["s1"],levels["s2"],levels["s3"]],"resistance":[levels["r1"],levels["r2"],levels["r3"]],
            "reason":"; ".join(reasons),"method":"Classic · Trend + Pivot + SNR + RSI + MACD + EMA + Candlestick"}

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
        if any((GROQ_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY, MISTRAL_API_KEY, CEREBRAS_API_KEY, CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN, DEEPSEEK_API_KEY, OPENAI_API_KEY)):
            try:
                text, ai_provider = await ai_json_completion(prompt)
                if text:
                    try:
                        parsed = json.loads(text)
                        result = {"mode": ai_provider, **parsed}
                    except json.JSONDecodeError:
                        result = {
                            "mode": ai_provider, "summary": text,
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



AI_SIGNAL_CACHE: dict[str, tuple[float, str | None, dict[str, Any]]] = {}
AI_SIGNAL_LOCKS: dict[str, asyncio.Lock] = {}
AI_SIGNAL_LOCKS_GUARD = asyncio.Lock()

async def ai_validate_module_signal(source: str, symbol: str, interval: str, candle_time: Any, deterministic: dict[str, Any]) -> dict[str, Any]:
    """Independent AI validator shared by every signal module.
    It never fetches market data itself: only the supplied TradingView-derived
    OHLC/quantitative context is evaluated. One request is cached per closed candle.
    """
    key=f"module|{source}|{clean_symbol(symbol)}|{validate_interval(interval)}"
    async with AI_SIGNAL_LOCKS_GUARD:
        lock=AI_SIGNAL_LOCKS.setdefault(key, asyncio.Lock())
    async with lock:
        now=datetime.now(timezone.utc).timestamp()
        cached=AI_SIGNAL_CACHE.get(key)
        if cached and cached[1] == str(candle_time) and now-cached[0] < AI_CACHE_TTL:
            return dict(cached[2])
        base_signal=str(deterministic.get("signal", "WAIT")).upper()
        context={
            "source":source,"symbol":clean_symbol(symbol),"timeframe":validate_interval(interval),
            "candle_time":candle_time,"deterministic_signal":base_signal,
            "deterministic_confidence":deterministic.get("confidence",0),
            "entry":deterministic.get("entry"),"stop_loss":deterministic.get("stop_loss"),
            "take_profit":deterministic.get("take_profit",[]),
            "reason":deterministic.get("reason",""),
            "technical": {k:v for k,v in deterministic.items() if k not in {"recent_candles","candles"}},
        }
        result=None
        if (GROQ_API_KEY or OPENAI_API_KEY) and now >= OPENAI_GLOBAL_RATE_LIMIT_UNTIL:
            try:
                prompt=("You are the validation layer of a quantitative XAU/USD trading system. "
                    "Evaluate ONLY the supplied deterministic analysis. Do not invent prices or external news. "
                    "Return JSON only: signal (BUY/SELL/WAIT), confidence (0-100 integer), agreement (0-100 integer), "
                    "risk_flags (array of short strings), reasoning (short string). "
                    "Be conservative: if evidence conflicts or the setup is weak, return WAIT. "
                    "This is analysis, not a guarantee.\n\n"+json.dumps(context,ensure_ascii=False,default=str))
                text, ai_provider = await ai_json_completion(prompt)
                parsed=json.loads(text)
                sig=str(parsed.get("signal","WAIT")).upper()
                result={"mode":ai_provider,"signal":sig if sig in {"BUY","SELL","WAIT"} else "WAIT",
                        "confidence":max(0,min(100,int(parsed.get("confidence",0)))),
                        "agreement":max(0,min(100,int(parsed.get("agreement",0)))),
                        "risk_flags":parsed.get("risk_flags",[]) if isinstance(parsed.get("risk_flags",[]),list) else [],
                        "reasoning":str(parsed.get("reasoning","AI validation."))}
            except Exception as exc:
                msg=str(exc)
                if "429" in msg or "rate limit" in msg.lower():
                    globals()["OPENAI_GLOBAL_RATE_LIMIT_UNTIL"]=now+OPENAI_GLOBAL_RATE_LIMIT_SECONDS
                result={"mode":"fallback","signal":base_signal if base_signal in {"BUY","SELL"} else "WAIT",
                        "confidence":int(deterministic.get("confidence",0) or 0),"agreement":50,
                        "risk_flags":["AI provider unavailable"],"reasoning":"Deterministic quantitative validation used."}
        else:
            result={"mode":"rule_based","signal":base_signal if base_signal in {"BUY","SELL"} else "WAIT",
                    "confidence":int(deterministic.get("confidence",0) or 0),"agreement":50,
                    "risk_flags":[],"reasoning":"AI API unavailable or cooldown active; quantitative engine retained."}
        AI_SIGNAL_CACHE[key]=(now,str(candle_time),result)
        return dict(result)


def merge_ai_validation(deterministic: dict[str, Any], ai: dict[str, Any]) -> dict[str, Any]:
    """Conservative ensemble: disagreement downgrades to WAIT; agreement can raise confidence modestly."""
    out=dict(deterministic); base=str(out.get("signal","WAIT")).upper(); ais=str(ai.get("signal","WAIT")).upper()
    out["ai_validation"]=ai
    if base in {"BUY","SELL"} and ais in {"BUY","SELL"} and ais != base:
        out["pre_ai_signal"]=base; out["signal"]="WAIT"; out["ai_consensus"]="CONFLICT"; out["confidence"]=min(int(out.get("confidence",0) or 0),79)
    elif base in {"BUY","SELL"} and ais==base:
        out["ai_consensus"]="CONFIRMED"; out["confidence"]=min(99,max(int(out.get("confidence",0) or 0), round((int(out.get("confidence",0) or 0)*0.7)+(int(ai.get("confidence",0) or 0)*0.3))))
    else:
        out["ai_consensus"]="WAIT"
    out["reason"]=((out.get("reason") or "") + f" | AI validation: {out['ai_consensus']} ({ai.get('confidence',0)}%).").strip()
    return out


def _normalize_swing_point(point: Any) -> tuple[int, float] | None:
    """Normalize swing points from any legacy/current representation to (index, price)."""
    try:
        if isinstance(point, dict):
            idx = point.get("index", point.get("i"))
            val = point.get("price", point.get("value", point.get("v")))
            if idx is None or val is None:
                return None
            # Some legacy payloads nested the index inside a tuple/list.
            if isinstance(idx, (tuple, list)):
                idx = idx[0]
            return int(idx), float(val)
        if isinstance(point, (tuple, list)) and len(point) >= 2:
            idx, val = point[0], point[1]
            if isinstance(idx, (tuple, list)):
                idx = idx[0]
            if isinstance(val, (tuple, list)):
                val = val[-1]
            return int(idx), float(val)
    except (TypeError, ValueError, IndexError):
        return None
    return None


def _swing_points(candles: list[dict[str, Any]], left: int = 2, right: int = 2) -> tuple[list[tuple[int,float]], list[tuple[int,float]]]:
    highs=[]; lows=[]
    n=len(candles)
    for i in range(left, n-right):
        hi=float(candles[i]["high"]); lo=float(candles[i]["low"])
        if hi >= max(float(candles[j]["high"]) for j in range(i-left,i+right+1)):
            highs.append((int(i),hi))
        if lo <= min(float(candles[j]["low"]) for j in range(i-left,i+right+1)):
            lows.append((int(i),lo))
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



def _fibonacci_analysis(candles: list[dict[str, Any]]) -> dict[str, Any]:
    """Strict per-timeframe Fibonacci engine.

    The Fibonacci is calculated ONLY from the candles supplied for this
    timeframe.  It is anchored to the latest confirmed dominant impulse:
    bullish = swing low -> later swing high, bearish = swing high -> later
    swing low.  The anchor is changed only when a newer valid structural
    impulse appears; ordinary candles do not drag the anchors around.
    """
    n = len(candles)
    if n < 40:
        return {"available": False, "direction": "NEUTRAL", "reason": "Yetarli candle yo'q"}

    raw_highs, raw_lows = _swing_points(candles)
    highs = []
    lows = []
    for pt in raw_highs:
        norm = _normalize_swing_point(pt)
        if norm and 2 <= norm[0] < n - 2:
            highs.append(norm)
    for pt in raw_lows:
        norm = _normalize_swing_point(pt)
        if norm and 2 <= norm[0] < n - 2:
            lows.append(norm)
    if not highs or not lows:
        return {"available": False, "direction": "NEUTRAL", "reason": "Valid swing topilmadi"}

    structure = _structure_state(candles)
    # Determine direction from confirmed swing sequence first, then BOS/CHOCH.
    direction = "NEUTRAL"
    if len(highs) >= 2 and len(lows) >= 2:
        hh = highs[-1][1] > highs[-2][1]
        hl = lows[-1][1] > lows[-2][1]
        lh = highs[-1][1] < highs[-2][1]
        ll = lows[-1][1] < lows[-2][1]
        if hh and hl:
            direction = "BULLISH"
        elif lh and ll:
            direction = "BEARISH"
    if direction == "NEUTRAL":
        if structure.get("choch") == "BULLISH" or structure.get("bos") == "BULLISH":
            direction = "BULLISH"
        elif structure.get("choch") == "BEARISH" or structure.get("bos") == "BEARISH":
            direction = "BEARISH"

    anchor_low = None
    anchor_high = None

    if direction == "BULLISH":
        # Latest confirmed swing high and the latest confirmed swing low BEFORE it.
        for high in reversed(highs):
            before = [low for low in lows if low[0] < high[0]]
            if before:
                candidate_low = before[-1]
                # Ignore tiny/noisy impulses; prefer the latest meaningful leg.
                if high[1] > candidate_low[1]:
                    anchor_low, anchor_high = candidate_low, high
                    break
    elif direction == "BEARISH":
        # Latest confirmed swing low and the latest confirmed swing high BEFORE it.
        for low in reversed(lows):
            before = [high for high in highs if high[0] < low[0]]
            if before:
                candidate_high = before[-1]
                if candidate_high[1] > low[1]:
                    anchor_high, anchor_low = candidate_high, low
                    break

    if anchor_low is None or anchor_high is None:
        return {"available": False, "direction": direction, "reason": "Yangi valid dominant impulse topilmadi"}

    low = float(anchor_low[1])
    high = float(anchor_high[1])
    rng = abs(high - low)
    if rng <= 0:
        return {"available": False, "direction": direction, "reason": "Fibonacci range nol"}

    # Standard retracement + extension levels from the supplied strategy.
    levels = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.272, 1.618]
    if direction == "BULLISH":
        prices = {str(x): high - rng * x for x in levels}
    else:
        prices = {str(x): low + rng * x for x in levels}

    current = float(candles[-1]["close"])
    key = [0.382, 0.5, 0.618, 0.786]
    nearest = min(key, key=lambda x: abs(current - prices[str(x)]))

    # The key entry zone is strictly 50%-61.8%. Keep the zone narrow and
    # proportional to this timeframe's own impulse, rather than extending it
    # across the entire chart with a large volatility padding.
    zone_base_low = min(prices["0.5"], prices["0.618"])
    zone_base_high = max(prices["0.5"], prices["0.618"])
    zone_pad = min(rng * 0.012, max(rng * 0.004, current * 0.00012))
    zone_lo = zone_base_low - zone_pad
    zone_hi = zone_base_high + zone_pad
    in_zone = zone_lo <= current <= zone_hi

    prev_close = float(candles[-2]["close"]) if n > 1 else current
    last_open = float(candles[-1]["open"])
    bullish_candle = current > last_open and current > prev_close
    bearish_candle = current < last_open and current < prev_close
    confirmation = (
        "BUY" if direction == "BULLISH" and in_zone and bullish_candle
        else "SELL" if direction == "BEARISH" and in_zone and bearish_candle
        else "WAIT"
    )

    closes = [float(c["close"]) for c in candles[-15:]]
    gains, losses = [], []
    for a, b in zip(closes[:-1], closes[1:]):
        d = b - a
        gains.append(max(d, 0.0)); losses.append(max(-d, 0.0))
    avg_gain = sum(gains) / max(len(gains), 1)
    avg_loss = sum(losses) / max(len(losses), 1)
    rsi = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    rsi_ok = (direction == "BULLISH" and rsi >= 50) or (direction == "BEARISH" and rsi <= 50)

    # Only draw the Fibonacci over the current structural impulse window, not
    # from the first candle in the chart. This keeps the visual zones short.
    draw_start_index = min(anchor_low[0], anchor_high[0])
    draw_end_index = n - 1
    retracement_zone = {
        "low": round(zone_lo, 4),
        "high": round(zone_hi, 4),
        "base_low": round(zone_base_low, 4),
        "base_high": round(zone_base_high, 4),
        "padding": round(zone_pad, 4),
    }

    return {
        "available": True,
        "direction": direction,
        "anchor_low": {"index": anchor_low[0], "time": candles[anchor_low[0]].get("time"), "price": round(low, 4)},
        "anchor_high": {"index": anchor_high[0], "time": candles[anchor_high[0]].get("time"), "price": round(high, 4)},
        "range": round(rng, 4),
        "levels": {k: round(v, 4) for k, v in prices.items()},
        "retracement_zone": retracement_zone,
        "nearest_level": nearest,
        "price_at_level": round(prices[str(nearest)], 4),
        "current_price": round(current, 4),
        "in_zone": in_zone,
        "signal": confirmation,
        "confirmation": confirmation,
        "price_action_confirmation": bullish_candle if direction == "BULLISH" else bearish_candle,
        "rsi": round(rsi, 2),
        "rsi_ok": rsi_ok,
        "extension_targets": {"1.272": round(prices["1.272"], 4), "1.618": round(prices["1.618"], 4)},
        "structure": structure,
        "draw_start_index": draw_start_index,
        "draw_end_index": draw_end_index,
        "draw_start_time": candles[draw_start_index].get("time"),
        "draw_end_time": candles[draw_end_index].get("time"),
        "reason": f"{direction} structure · dominant impulse · Fibonacci {nearest:.3f} · "
                  f"{'50-61.8% ZONE' if in_zone else 'WAIT'} · "
                  f"{'CANDLE CONFIRMED' if confirmation != 'WAIT' else 'WAIT CONFIRMATION'}"
    }

def _snr(candles: list[dict[str, Any]]) -> dict[str, Any]:
    """Strong-zone SNR levels. Prefer repeatedly tested swing clusters over one-off extremes."""
    z=_snr_zone_analysis(candles)
    return {
        "support": z["support"]["mid"],
        "resistance": z["resistance"]["mid"],
        "support_zone": z["support"],
        "resistance_zone": z["resistance"],
        "signal": z["signal"],
        "confidence": z["confidence"],
        "position": z["position"],
    }


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


def _trendline_point_value(p1: tuple[int,float], p2: tuple[int,float], idx: int) -> float:
    i1,v1=p1; i2,v2=p2
    if i2 == i1:
        return v2
    return v1 + (v2-v1) * ((idx-i1)/(i2-i1))


def _trendline_analysis(candles: list[dict[str, Any]]) -> dict[str, Any]:
    """Strict per-timeframe trend-line engine.

    IMPORTANT: this function receives candles from ONE validated timeframe only.
    It never mixes M5/M15/H1/H4/D1 candles.  The line is anchored to confirmed
    swing points of that same series and is selected from the current structural
    direction, not from an arbitrary recent line with the most touches.

    Rules:
      * bullish structure -> support through higher swing lows
      * bearish structure -> resistance through lower swing highs
      * minimum 2 anchor touches; extra touches increase quality
      * breakout is close-based (wick alone is not a breakout)
      * retest must occur after the breakout
    """
    n=len(candles)
    base={"available":False,"trend":"NEUTRAL","type":"NONE","touches":0,"trend_power":0,
          "breakout":"NO","retest":"NO","confirmation":"WAIT","signal":"WAIT"}
    if n < 40:
        return {**base,"reason":"Yetarli candle yo'q"}

    raw_highs,raw_lows=_swing_points(candles)
    highs=[]; lows=[]
    for pt in raw_highs:
        norm=_normalize_swing_point(pt)
        if norm and 2 <= norm[0] < n-2: highs.append(norm)
    for pt in raw_lows:
        norm=_normalize_swing_point(pt)
        if norm and 2 <= norm[0] < n-2: lows.append(norm)
    if len(highs)<2 and len(lows)<2:
        return {**base,"reason":"Valid swing topilmadi"}

    atrv=max(atr(candles), float(candles[-1]["close"])*0.0003)
    tol=max(atrv*0.16, float(candles[-1]["close"])*0.00030)

    def structure_direction():
        # Use the latest two confirmed highs/lows. This prevents an old line from
        # being selected just because it happens to have many historical touches.
        hh = len(highs)>=2 and highs[-1][1] > highs[-2][1]
        hl = len(lows)>=2 and lows[-1][1] > lows[-2][1]
        lh = len(highs)>=2 and highs[-1][1] < highs[-2][1]
        ll = len(lows)>=2 and lows[-1][1] < lows[-2][1]
        if hh and hl: return "BULLISH"
        if lh and ll: return "BEARISH"
        # If one side is ambiguous, use the latest confirmed sequence as a
        # secondary tie-breaker, while still requiring two pivots.
        if hl and not lh: return "BULLISH"
        if lh and not hl: return "BEARISH"
        return "NEUTRAL"

    direction=structure_direction()

    def line_candidate(points, mode):
        if len(points)<2: return None
        # Prefer the latest two structurally valid pivots. If those fail the
        # touch test, search a small recent window, but never older than 12 pivots.
        candidates=[]
        recent=points[-12:]
        for a in range(max(0,len(recent)-8),len(recent)-1):
            for b in range(a+1,len(recent)):
                p1,p2=recent[a],recent[b]
                if p2[0]-p1[0] < 4: continue
                if mode=="UP" and p2[1] <= p1[1]: continue
                if mode=="DOWN" and p2[1] >= p1[1]: continue
                slope=(p2[1]-p1[1])/(p2[0]-p1[0])
                # Count touches on the actual swing points plus intervening
                # candles. Anchors are always counted as touches.
                touch_idxs=[p1[0],p2[0]]
                for i in range(p1[0]+1,n):
                    if i in (p2[0],): continue
                    lv=_trendline_point_value(p1,p2,i)
                    price=float(candles[i]["low"] if mode=="UP" else candles[i]["high"])
                    if abs(price-lv)<=tol: touch_idxs.append(i)
                touch_idxs=sorted(set(touch_idxs))
                # A candidate must not be badly crossed by price after p2.
                violations=0
                for i in range(p2[0]+1,n):
                    lv=_trendline_point_value(p1,p2,i)
                    if mode=="UP" and float(candles[i]["close"]) < lv-tol*0.9: violations+=1
                    if mode=="DOWN" and float(candles[i]["close"]) > lv+tol*0.9: violations+=1
                # At least the two anchors. Prefer recent anchors, more touches,
                # longer clean support/resistance, and fewer structural violations.
                span=n-p2[0]
                recency=max(0,20-(n-p2[0]))
                quality=(touch_idxs.__len__()*28 + min(20,span/5) + recency
                         - min(35,violations*4) + min(10,abs(slope)*700))
                candidates.append((quality,p1,p2,slope,touch_idxs,violations))
        if not candidates: return None
        # Primary priority: most recent p2, then touches, then quality.
        candidates.sort(key=lambda x:(x[2][0],len(x[4]),x[0]),reverse=True)
        return candidates[0]

    # Directional line first. In a neutral structure we may show the strongest
    # valid line, but it cannot produce a directional signal by itself.
    if direction=="BULLISH":
        chosen=line_candidate(lows,"UP"); mode="UP"
    elif direction=="BEARISH":
        chosen=line_candidate(highs,"DOWN"); mode="DOWN"
    else:
        up=line_candidate(lows,"UP"); down=line_candidate(highs,"DOWN")
        if up and down:
            chosen=up if up[2][0]>=down[2][0] else down
            mode="UP" if chosen is up else "DOWN"
        elif up:
            chosen=up; mode="UP"
        elif down:
            chosen=down; mode="DOWN"
        else:
            chosen=None; mode="NONE"

    if chosen is None:
        return {**base,"reason":"Valid 2-touch trend line topilmadi"}

    quality,p1,p2,slope,touch_idxs,violations=chosen
    touches=len(touch_idxs)
    current_i=n-1; prev_i=n-2
    line_prev=_trendline_point_value(p1,p2,prev_i); line_cur=_trendline_point_value(p1,p2,current_i)
    prev_close=float(candles[prev_i]["close"]); cur_close=float(candles[current_i]["close"])
    breakout="NO"; retest="NO"; confirmation="WAIT"; breakout_idx=None; retest_idx=None

    # Confirmed close breakout only. The current candle is already closed by the
    # caller, so it is safe to use its close here.
    if mode=="UP" and prev_close >= line_prev-tol and cur_close < line_cur-tol*0.35:
        breakout="BEARISH_BREAK"; breakout_idx=current_i
    elif mode=="DOWN" and prev_close <= line_prev+tol and cur_close > line_cur+tol*0.35:
        breakout="BULLISH_BREAK"; breakout_idx=current_i

    # Look for the most recent close-based breakout in the last 12 candles if the
    # current candle itself did not break. This keeps the retest sequence causal.
    if breakout_idx is None:
        look_start=max(p2[0]+1,n-12)
        for i in range(look_start,n-1):
            lp=_trendline_point_value(p1,p2,i)
            prev_c=float(candles[i-1]["close"]) if i>0 else float(candles[i]["close"])
            c=float(candles[i]["close"])
            if mode=="UP" and prev_c>=lp-tol and c<lp-tol*0.35:
                breakout_idx=i; breakout="BEARISH_BREAK"
            elif mode=="DOWN" and prev_c<=lp+tol and c>lp+tol*0.35:
                breakout_idx=i; breakout="BULLISH_BREAK"
            if breakout_idx is not None: break

    if breakout_idx is not None and breakout_idx < n-1:
        for i in range(breakout_idx+1,n):
            lv=_trendline_point_value(p1,p2,i)
            c=float(candles[i]["close"]); hi=float(candles[i]["high"]); lo=float(candles[i]["low"])
            # Retest can touch the line with wick, but the close must remain on
            # the broken side for confirmation.
            touched=lo<=lv+tol and hi>=lv-tol
            if not touched: continue
            if mode=="UP" and c < lv-tol*0.15:
                retest="YES"; retest_idx=i; confirmation="CONFIRMED_SELL"
            elif mode=="DOWN" and c > lv+tol*0.15:
                retest="YES"; retest_idx=i; confirmation="CONFIRMED_BUY"
            if retest_idx is not None: break

    if breakout=="NO":
        if mode=="UP" and cur_close > line_cur-tol*0.15: confirmation="BULLISH_HOLD"
        elif mode=="DOWN" and cur_close < line_cur+tol*0.15: confirmation="BEARISH_HOLD"

    # In neutral structure, the line is informational only.
    if direction=="NEUTRAL" and confirmation in {"BULLISH_HOLD","BEARISH_HOLD"}:
        confirmation="WAIT"

    power=int(max(0,min(99,round(
        45 + min(30,touches*9) + min(12,max(0,(n-p2[0]))/5)
        + (10 if breakout!="NO" else 0) + (8 if retest=="YES" else 0)
        - min(20,violations*2)
    ))))
    trend="BULLISH" if mode=="UP" else "BEARISH" if mode=="DOWN" else "NEUTRAL"
    sig="BUY" if confirmation in {"CONFIRMED_BUY","BULLISH_HOLD"} and direction=="BULLISH" else "SELL" if confirmation in {"CONFIRMED_SELL","BEARISH_HOLD"} and direction=="BEARISH" else "WAIT"

    swing_highs=[{"index":pt[0],"time":candles[pt[0]].get("time"),"price":round(pt[1],4)} for pt in highs[-20:]]
    swing_lows=[{"index":pt[0],"time":candles[pt[0]].get("time"),"price":round(pt[1],4)} for pt in lows[-20:]]
    return {"available":True,"trend":trend,"type":"SUPPORT" if mode=="UP" else "RESISTANCE" if mode=="DOWN" else "NONE",
            "p1":{"index":p1[0],"time":candles[p1[0]].get("time"),"price":round(p1[1],4)},
            "p2":{"index":p2[0],"time":candles[p2[0]].get("time"),"price":round(p2[1],4)},
            "slope":round(slope,8),"touches":touches,"touch_indices":touch_idxs[-12:],
            "swing_highs":swing_highs,"swing_lows":swing_lows,
            "breakout_index":breakout_idx,"retest_index":retest_idx,
            "trend_power":power,"breakout":breakout,"retest":retest,"confirmation":confirmation,
            "current_line":round(line_cur,4),"signal":sig,
            "timeframe_candles":n,
            "reason":f"{('Support' if mode=='UP' else 'Resistance' if mode=='DOWN' else 'Neutral')} trend line · {touches} touch · power {power}% · structure {direction} · {breakout} · retest {retest}."}


def _snr_zone_analysis(candles: list[dict[str, Any]]) -> dict[str, Any]:
    current=float(candles[-1]["close"]); highs,lows=_swing_points(candles,2,2); avtr=max(atr(candles), current*0.0004)
    high_vals=[float(v) for _,v in highs[-24:]] or [float(candles[-1]["high"])]
    low_vals=[float(v) for _,v in lows[-24:]] or [float(candles[-1]["low"])]
    width=max(avtr*0.28, current*0.00045)
    def best_cluster(vals, side):
        # Score each swing level by repeated touches, recency and separation from price.
        candidates=[]
        for level in vals:
            lo,hi=level-width,level+width
            touches=sum(1 for v in vals if lo<=v<=hi)
            recency=sum(1 for c in candles[-60:] if lo<=float(c["low" if side=="support" else "high"])<=hi)
            distance=abs(current-level)/max(current,1e-9)
            candidates.append((touches*12+min(recency,10)*3-min(distance*1000,18),level,touches,recency))
        return max(candidates,key=lambda x:x[0]) if candidates else (0,float(candles[-1]["close"]),0,0)
    _,support,sret,srec=best_cluster(low_vals,"support")
    _,resistance,rret,rrec=best_cluster(high_vals,"resistance")
    def zone(level,side,retests,recency):
        lo,hi=level-width,level+width
        in_zone=lo<=current<=hi
        dist=abs(current-level)/max(current,1e-9)*100
        proximity=max(0,18-dist*160)
        strength=min(99,round(48+retests*7+min(recency,10)*2.5+proximity+(10 if in_zone else 0)))
        if side=="support": status="IN ZONE" if in_zone else "BROKEN" if current<lo else "ACTIVE"
        else: status="IN ZONE" if in_zone else "BROKEN" if current>hi else "ACTIVE"
        return {"mid":round(level,4),"low":round(lo,4),"high":round(hi,4),"retests":int(retests),"strength":int(strength),"distance_pct":round(dist,3),"status":status,"quality":"STRONG" if strength>=82 else "GOOD" if strength>=72 else "WEAK"}
    sup,res=zone(support,"support",sret,srec),zone(resistance,"resistance",rret,rrec)
    # A signal is allowed only at a strong zone or a clean breakout of a strong zone.
    bullish_zone=sup["strength"]>=82 and (sup["status"]=="IN ZONE" or current>sup["high"])
    bearish_zone=res["strength"]>=82 and (res["status"]=="IN ZONE" or current<res["low"])
    if sup["status"]=="IN ZONE" and sup["strength"]>=82: signal="BUY"
    elif res["status"]=="IN ZONE" and res["strength"]>=82: signal="SELL"
    elif current>res["high"] and res["strength"]>=82: signal="BUY"
    elif current<sup["low"] and sup["strength"]>=82: signal="SELL"
    else: signal="WAIT"
    confidence=max(sup["strength"],res["strength"]) if signal!="WAIT" else round((sup["strength"]+res["strength"])/2)
    pos="ABOVE RESISTANCE" if current>res["high"] else "BELOW SUPPORT" if current<sup["low"] else "NEAR SUPPORT" if current<=sup["mid"] else "NEAR RESISTANCE" if current>=res["mid"] else "BETWEEN ZONES"
    if signal=="BUY": entry=current; stop_loss=sup["low"]; take_profit=[res["mid"],res["high"]]
    elif signal=="SELL": entry=current; stop_loss=res["high"]; take_profit=[sup["mid"],sup["low"]]
    else: entry=current; stop_loss=None; take_profit=[]
    strongest=max(sup,res,key=lambda z:z["strength"])
    reason=f"{pos.lower()}; strongest zone {strongest['strength']}% ({strongest['quality']}); Support {sup['strength']}% · Resistance {res['strength']}%."
    return {"support":sup,"resistance":res,"signal":signal,"confidence":confidence,"position":pos,
            "entry":round(entry,4),"stop_loss":round(stop_loss,4) if stop_loss is not None else None,
            "take_profit":[round(v,4) for v in take_profit],
            "strongest_zone":strongest,"reason":reason,"method":"Strong-zone SNR · clustered swings + retests + proximity + volatility"}


def build_advanced_signal(candles: list[dict[str, Any]], interval: str, news_blocked: bool=False) -> dict[str, Any]:
    current=float(candles[-1]["close"])
    avtr=max(atr(candles), current*0.0004)
    snr=_snr(candles); msnr=_snr_malaysia(candles)
    structure=_structure_state(candles)
    fvg=_detect_fvg(candles)
    ob=_detect_order_block(candles,avtr)
    highs,lows=_swing_points(candles)
    trendline=_trendline_analysis(candles)
    fibonacci=_fibonacci_analysis(candles)
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
    if trendline.get("trend")=="BULLISH": score+=2; reasons.append("bullish support trend line")
    elif trendline.get("trend")=="BEARISH": score-=2; reasons.append("bearish resistance trend line")
    if trendline.get("signal")=="BUY": score+=1; reasons.append("trend line buy confirmation")
    elif trendline.get("signal")=="SELL": score-=1; reasons.append("trend line sell confirmation")

    zone_gate=_snr_zone_analysis(candles)
    strong_buy_zone=zone_gate["support"]["strength"]>=82 and (zone_gate["support"]["status"]=="IN ZONE" or zone_gate["support"]["distance_pct"]<=0.9)
    strong_sell_zone=zone_gate["resistance"]["strength"]>=82 and (zone_gate["resistance"]["status"]=="IN ZONE" or zone_gate["resistance"]["distance_pct"]<=0.9)
    confidence=min(99,max(35,50+abs(score)*5 + (8 if (strong_buy_zone or strong_sell_zone) else 0)))
    direction="BUY" if score>=8 else "SELL" if score<=-8 else "WAIT"
    if direction=="BUY" and not strong_buy_zone: direction="WAIT"; reasons.append("WAIT: no strong support entry zone")
    if direction=="SELL" and not strong_sell_zone: direction="WAIT"; reasons.append("WAIT: no strong resistance entry zone")
    if direction=="BUY" and r < 55: direction="WAIT"; reasons.append("WAIT: RSI not supportive for BUY")
    if direction=="SELL" and r > 45: direction="WAIT"; reasons.append("WAIT: RSI not supportive for SELL")
    if direction=="BUY" and trend!="BULLISH": direction="WAIT"; reasons.append("WAIT: local trend not bullish")
    if direction=="SELL" and trend!="BEARISH": direction="WAIT"; reasons.append("WAIT: local trend not bearish")
    if direction=="BUY" and global_trend!="BULLISH": direction="WAIT"; reasons.append("WAIT: global trend not bullish")
    if direction=="SELL" and global_trend!="BEARISH": direction="WAIT"; reasons.append("WAIT: global trend not bearish")
    if direction=="BUY" and trendline.get("trend")=="BEARISH": direction="WAIT"; reasons.append("WAIT: trend line bearish filter")
    if direction=="SELL" and trendline.get("trend")=="BULLISH": direction="WAIT"; reasons.append("WAIT: trend line bullish filter")
    if direction=="BUY" and fibonacci.get("direction")=="BEARISH": direction="WAIT"; reasons.append("WAIT: Fibonacci bearish structure")
    if direction=="SELL" and fibonacci.get("direction")=="BULLISH": direction="WAIT"; reasons.append("WAIT: Fibonacci bullish structure")
    if trendline.get("trend_power",0) >= 80 and trendline.get("signal") not in {"BUY","SELL"} and direction in {"BUY","SELL"}:
        if direction=="BUY" and trendline.get("trend")!="BULLISH": direction="WAIT"
        if direction=="SELL" and trendline.get("trend")!="BEARISH": direction="WAIT"
    if news_blocked: direction="WAIT"
    entry=current
    swing_low=structure["swing_low"]; swing_high=structure["swing_high"]
    if direction=="BUY":
        sl=min(swing_low, current-avtr*1.2); risk=max(entry-sl,avtr*0.6); tp=[entry+risk*1.5,entry+risk*2.5]
    elif direction=="SELL":
        sl=max(swing_high, current+avtr*1.2); risk=max(sl-entry,avtr*0.6); tp=[entry-risk*1.5,entry-risk*2.5]
    else:
        sl=None; tp=[]
    rr = (abs((tp[0]-entry)/(entry-sl)) if direction=="BUY" and sl is not None and tp else abs((entry-tp[0])/(sl-entry)) if direction=="SELL" and sl is not None and tp else 0.0)
    confirmations = sum([
        1 if (direction=="BUY" and liq["type"]=="SELL_SIDE_SWEEP") or (direction=="SELL" and liq["type"]=="BUY_SIDE_SWEEP") else 0,
        1 if (direction=="BUY" and ob["type"]=="BULLISH") or (direction=="SELL" and ob["type"]=="BEARISH") else 0,
        1 if (direction=="BUY" and fvg["type"]=="BULLISH") or (direction=="SELL" and fvg["type"]=="BEARISH") else 0,
        1 if (direction=="BUY" and structure["bos"]=="BULLISH") or (direction=="SELL" and structure["bos"]=="BEARISH") else 0,
        1 if (direction=="BUY" and trend=="BULLISH") or (direction=="SELL" and trend=="BEARISH") else 0,
        1 if (direction=="BUY" and global_trend=="BULLISH") or (direction=="SELL" and global_trend=="BEARISH") else 0,
        1 if (direction=="BUY" and trendline.get("trend")=="BULLISH") or (direction=="SELL" and trendline.get("trend")=="BEARISH") else 0,
        1 if (direction=="BUY" and trendline.get("signal")=="BUY") or (direction=="SELL" and trendline.get("signal")=="SELL") else 0,
    ]) if direction!="WAIT" else 0
    setup="ULTRA_CONFLUENCE" if direction!="WAIT" and confirmations>=5 and rr>=1.5 else ("ICT+SNR+CONFLUENCE" if direction!="WAIT" else ("NEWS_BLACKOUT" if news_blocked else "WAIT_CONFLUENCE"))
    quality="A+" if direction!="WAIT" and confidence>=90 and max(zone_gate["support"]["strength"],zone_gate["resistance"]["strength"])>=88 and confirmations>=5 and rr>=1.5 else "A" if direction!="WAIT" else "WAIT"
    return {
        "interval":interval,"signal":direction,"entry":round(entry,4),"stop_loss":round(sl,4) if sl is not None else None,
        "take_profit":[round(x,4) for x in tp],"confidence":confidence,"score":score,"setup":setup,
        "components":{"ICT":ict_bias,"SNR":snr,"Strong SNR Zone":zone_gate,"SNR Malaysia":msnr,"Order Block":ob,"FVG":fvg,"Liquidity":liq,
                       "Trend Line":trendline,"Fibonacci":fibonacci,"Trend":trend,"Global Trend Line":global_trend,"BOS":structure["bos"],"CHOCH":structure["choch"],"Internal Structure":structure["internal_structure"]},
        "trendline":trendline,
        "fibonacci":fibonacci,
        "zone_quality":max(zone_gate["support"]["strength"],zone_gate["resistance"]["strength"]),
        "entry_zone":zone_gate["strongest_zone"],
        "risk_reward":round(rr,2),
        "confirmations":confirmations,
        "quality_grade":quality,
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
            closed_candles=candles_data[:-1] if len(candles_data)>1 else candles_data
            item=build_advanced_signal(closed_candles,tf,news_blocked=news_blocked)
            candle_time=closed_candles[-1].get("time")
            ai=await ai_validate_module_signal("Signal Lab",symbol,tf,candle_time,item)
            item=merge_ai_validation(item,ai)
            item["candle_time"]=candle_time
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
            if any((GROQ_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY, MISTRAL_API_KEY, CEREBRAS_API_KEY, CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN, DEEPSEEK_API_KEY, OPENAI_API_KEY)):
                try:
                    prompt = (
                        "You are the second-opinion validator for XAU/USD. "
                        "Use ONLY the supplied SIMPLE TRADING Book pattern result and recent OHLC candles. "
                        "Even if the Book signal is WAIT, still evaluate the supplied Book patterns and candles and return your own second opinion as BUY, SELL, or WAIT. "
                        "Do not add ICT, FVG, order blocks, liquidity, RSI, MACD, or any other strategy. "
                        "Return JSON only with keys signal (BUY/SELL/WAIT), confidence (0-100 integer), reason (short). "
                        "Do not invent price data.\n\n" +
                        json.dumps(context, ensure_ascii=False, default=str)
                    )
                    text, ai_provider = await ai_json_completion(prompt)
                    if text:
                        try:
                            parsed = json.loads(text)
                            sig = str(parsed.get("signal", "WAIT")).upper()
                            ai = {
                                "signal": sig if sig in {"BUY", "SELL", "WAIT"} else "WAIT",
                                "confidence": max(0, min(100, int(parsed.get("confidence", 0)))),
                                "reason": str(parsed.get("reason", "OpenAI second opinion.")),
                                "mode": ai_provider,
                            }
                        except Exception:
                            ai = {"signal": "WAIT", "confidence": 0, "reason": "OpenAI returned an invalid structured result.", "mode": ai_provider}
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
    ai = {"mode":"confirmation-only","summary":"AI faqat Auto Trading signal tasdig‘ida chaqiriladi.","bias":"—","confidence":0,"advice":"Oddiy sahifa/grafik refresh AI request yubormaydi."}
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

@app.get("/api/v1/snr/{symbol:path}")
async def get_snr(symbol: str, interval: str = Query(DEFAULT_INTERVAL)) -> dict[str, Any]:
    symbol=clean_symbol(symbol); interval=validate_interval(interval)
    try:
        candles,mode,warning=await get_candles(symbol,interval,220)
        if len(candles)<35: raise MarketDataError("SNR uchun candle yetarli emas")
        candle_time=candles[-2].get("time") if len(candles)>1 else candles[-1].get("time")
        snr=_snr_zone_analysis(candles)
        snr["ai_validation"] = None
        return {"ok":True,"symbol":symbol,"interval":interval,"mode":mode,"warning":warning,"current_price":round(float(candles[-1]["close"]),4),"candle_time":candle_time,"snr":snr,"generated_at":datetime.now(timezone.utc).isoformat()}
    except Exception as exc: raise HTTPException(status_code=503,detail="SNR unavailable: "+str(exc))

@app.get("/api/v1/classic-trade/{symbol:path}")
async def get_classic_trade(symbol: str, interval: str = Query(DEFAULT_INTERVAL)) -> dict[str, Any]:
    symbol = clean_symbol(symbol); interval = validate_interval(interval)
    try:
        candles, mode, warning = await get_candles(symbol, interval, 220)
        if len(candles) < 60: raise MarketDataError("Classic Trade uchun candle yetarli emas")
        ref = candles[-2]; price = float(candles[-1]["close"])
        levels = calculate_pivot_levels(float(ref["high"]), float(ref["low"]), float(ref["close"]), price)
        classic = _classic_trade(candles, levels)
        classic["ai_validation"] = None
        return {"ok":True,"symbol":symbol,"interval":interval,"mode":mode,"warning":warning,"current_price":round(price,4),"candle_time":ref.get("time"),"classic":classic,"generated_at":datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Classic Trade unavailable: "+str(exc))

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
        candle_time=candles_data[-2].get("time") if len(candles_data)>1 else candles_data[-1].get("time")
        technical["ai_validation"] = None
        return {
            "ok": True, "symbol": symbol, "interval": interval, "mode": "tradingview",
            "provider": "TradingView", "source": TRADINGVIEW_SYMBOL,
            "current_price": round(float(candles_data[-1]["close"]), 4),
            "candles": candles_data, "candle_time": candles_data[-2].get("time") if len(candles_data)>1 else candles_data[-1].get("time"), "levels": levels, "technical": technical,
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



# ---------------- ICT Signals: M30 -> M5 ----------------
def _ict_swings(candles: list[dict[str, Any]], window: int = 2):
    highs, lows = [], []
    for i in range(window, len(candles)-window):
        h=float(candles[i]["high"]); l=float(candles[i]["low"])
        if h >= max(float(candles[j]["high"]) for j in range(i-window,i+window+1)):
            highs.append((i,h))
        if l <= min(float(candles[j]["low"]) for j in range(i-window,i+window+1)):
            lows.append((i,l))
    return highs,lows

def _ict_fvg(candles: list[dict[str, Any]], lookback: int = 30):
    start=max(2,len(candles)-lookback)
    found=[]
    for i in range(start,len(candles)):
        a,b,c=candles[i-2],candles[i-1],candles[i]
        ah,al=float(a["high"]),float(a["low"])
        ch,cl=float(c["high"]),float(c["low"])
        if cl > ah:
            found.append({"type":"BULLISH","low":ah,"high":cl,"index":i})
        elif ch < al:
            found.append({"type":"BEARISH","low":ch,"high":al,"index":i})
    return found[-1] if found else {"type":"NONE","low":None,"high":None,"index":None}

def _ict_displacement(candles: list[dict[str, Any]], direction: str, period: int=14):
    if len(candles)<period+2: return False, 0.0
    a=max(atr(candles,period),float(candles[-1]["close"])*0.0002)
    c=candles[-1]
    body=abs(float(c["close"])-float(c["open"]))
    rng=max(float(c["high"])-float(c["low"]),1e-9)
    directional=(float(c["close"])>float(c["open"])) if direction=="BUY" else (float(c["close"])<float(c["open"]))
    return directional and body >= a*1.05 and body/rng >= 0.55, body/a

def _ict_mss(candles: list[dict[str, Any]], direction: str):
    highs,lows=_ict_swings(candles[:-1],2)
    if direction=="BUY" and highs:
        level=highs[-1][1]
        return float(candles[-1]["close"]) > level, level
    if direction=="SELL" and lows:
        level=lows[-1][1]
        return float(candles[-1]["close"]) < level, level
    return False,None

def _ict_liquidity_sweep(candles: list[dict[str, Any]], lookback:int=12):
    highs,lows=_ict_swings(candles[:-2],2)
    cur=candles[-1]
    hi=float(cur["high"]); lo=float(cur["low"]); close=float(cur["close"])
    recent_h=[x for x in highs if x[0] >= max(0,len(candles)-lookback-8)]
    recent_l=[x for x in lows if x[0] >= max(0,len(candles)-lookback-8)]
    if recent_h:
        level=recent_h[-1][1]
        if hi > level and close < level:
            return {"type":"BSL_SWEEP","level":level,"extreme":hi}
    if recent_l:
        level=recent_l[-1][1]
        if lo < level and close > level:
            return {"type":"SSL_SWEEP","level":level,"extreme":lo}
    return {"type":"NONE","level":None,"extreme":None}

def _ict_premium_discount(candles:list[dict[str,Any]], lookback:int=80):
    data=candles[-lookback:]
    hi=max(float(c["high"]) for c in data); lo=min(float(c["low"]) for c in data)
    mid=(hi+lo)/2
    price=float(candles[-1]["close"])
    return {"high":hi,"low":lo,"equilibrium":mid,
            "zone":"PREMIUM" if price>mid else "DISCOUNT",
            "position_pct":round((price-lo)/max(hi-lo,1e-9)*100,2)}

def _ict_order_block(candles:list[dict[str,Any]], direction:str, atr_value:float):
    # Last opposite candle before a strong directional candle.
    for i in range(len(candles)-2,max(-1,len(candles)-25),-1):
        c,n=candles[i],candles[i+1]
        co,cc=float(c["open"]),float(c["close"])
        no,nc=float(n["open"]),float(n["close"])
        body=abs(nc-no)
        if direction=="BUY" and cc<co and nc>no and body>=atr_value*0.8:
            return {"type":"BULLISH","low":float(c["low"]),"high":float(c["high"]),"index":i}
        if direction=="SELL" and cc>co and nc<no and body>=atr_value*0.8:
            return {"type":"BEARISH","low":float(c["low"]),"high":float(c["high"]),"index":i}
    return {"type":"NONE","low":None,"high":None,"index":None}

def _ict_target_liquidity(candles:list[dict[str,Any]], direction:str, entry:float):
    highs,lows=_ict_swings(candles,2)
    if direction=="BUY":
        vals=[v for _,v in highs if v>entry]
        return min(vals) if vals else None
    vals=[v for _,v in lows if v<entry]
    return max(vals) if vals else None

def build_ict_m30_m5(candles30:list[dict[str,Any]], candles5:list[dict[str,Any]]) -> dict[str,Any]:
    if len(candles30)<60 or len(candles5)<80:
        raise MarketDataError("ICT M30→M5 uchun kamida M30=60 va M5=80 candle kerak")
    p30=float(candles30[-1]["close"]); p5=float(candles5[-1]["close"])
    a30=max(atr(candles30),p30*0.0003); a5=max(atr(candles5),p5*0.0002)
    pd=_ict_premium_discount(candles30)
    h30,l30=_ict_swings(candles30[:-1],2)
    # HTF bias: structure plus EMA relationship, without forcing a trade.
    ema20=_ema([float(c["close"]) for c in candles30[-80:]],20)
    ema50=_ema([float(c["close"]) for c in candles30[-120:]],50)
    hvals=[v for _,v in h30[-3:]]; lvals=[v for _,v in l30[-3:]]
    bull_structure=len(hvals)>=2 and hvals[-1]>hvals[-2] and len(lvals)>=2 and lvals[-1]>lvals[-2]
    bear_structure=len(hvals)>=2 and hvals[-1]<hvals[-2] and len(lvals)>=2 and lvals[-1]<lvals[-2]
    bias="BULLISH" if bull_structure or (ema20>ema50 and p30>ema20) else "BEARISH" if bear_structure or (ema20<ema50 and p30<ema20) else "NEUTRAL"
    sweep=_ict_liquidity_sweep(candles30)
    fvg30=_ict_fvg(candles30)
    direction="BUY" if sweep["type"]=="SSL_SWEEP" else "SELL" if sweep["type"]=="BSL_SWEEP" else bias
    if direction not in ("BUY","SELL"): direction="WAIT"
    # Require HTF alignment where possible; a sweep can override a neutral bias but not a strong opposite structure.
    if direction=="BUY" and bias=="BEARISH" and bear_structure: direction="WAIT"
    if direction=="SELL" and bias=="BULLISH" and bull_structure: direction="WAIT"
    score=0; checks=[]; reasons=[]
    def add(name,pts,ok,reason):
        nonlocal score
        if ok: score+=pts; checks.append({"name":name,"points":pts,"status":"PASS"}); reasons.append(reason)
        else: checks.append({"name":name,"points":0,"status":"MISS"})
    add("M30 Bias",15,(direction=="BUY" and bias=="BULLISH") or (direction=="SELL" and bias=="BEARISH"),f"M30 bias {bias}")
    add("Liquidity Sweep",20,(direction=="BUY" and sweep["type"]=="SSL_SWEEP") or (direction=="SELL" and sweep["type"]=="BSL_SWEEP"),f"{sweep['type']} detected")
    add("Premium/Discount",10,(direction=="BUY" and pd["zone"]=="DISCOUNT") or (direction=="SELL" and pd["zone"]=="PREMIUM"),f"Price is in {pd['zone'].lower()} zone")
    add("M30 FVG",10,(fvg30["type"]==("BULLISH" if direction=="BUY" else "BEARISH")),f"M30 {fvg30['type']} FVG")
    ob30=_ict_order_block(candles30,"BUY" if direction=="BUY" else "SELL",a30) if direction!="WAIT" else {"type":"NONE"}
    add("M30 Order Block",10,ob30.get("type")==("BULLISH" if direction=="BUY" else "BEARISH"),f"M30 {ob30.get('type')} order block")
    disp5,disp_ratio=_ict_displacement(candles5,"BUY" if direction=="BUY" else "SELL") if direction!="WAIT" else (False,0)
    mss5,mss_level=_ict_mss(candles5,"BUY" if direction=="BUY" else "SELL") if direction!="WAIT" else (False,None)
    fvg5=_ict_fvg(candles5)
    add("M5 MSS",15,mss5,f"M5 {'bullish' if direction=='BUY' else 'bearish'} structure shift")
    add("M5 Displacement",10,disp5,f"M5 displacement ratio {disp_ratio:.2f} ATR")
    add("M5 FVG",10,fvg5["type"]==("BULLISH" if direction=="BUY" else "BEARISH"),f"M5 {fvg5['type']} FVG")
    target=_ict_target_liquidity(candles30 if direction!="WAIT" else candles5,direction,p5) if direction!="WAIT" else None
    # Entry uses the active M5 FVG midpoint when present; otherwise current price.
    entry=p5
    if direction!="WAIT" and fvg5["type"]==("BULLISH" if direction=="BUY" else "BEARISH"):
        entry=(fvg5["low"]+fvg5["high"])/2
    extreme=sweep["extreme"] if sweep["type"]!="NONE" else (min(float(c["low"]) for c in candles5[-8:]) if direction=="BUY" else max(float(c["high"]) for c in candles5[-8:]))
    if direction=="BUY":
        sl=min(extreme,entry-a5*1.1); risk=max(entry-sl,a5*0.7)
        tp1=target if target and target>entry+risk else entry+risk*1.5
        tp2=max(entry+risk*2.5,tp1+risk*0.5)
    elif direction=="SELL":
        sl=max(extreme,entry+a5*1.1); risk=max(sl-entry,a5*0.7)
        tp1=target if target and target<entry-risk else entry-risk*1.5
        tp2=min(entry-risk*2.5,tp1-risk*0.5)
    else:
        sl=None;tp1=tp2=None;risk=None
    confidence=min(99,score)
    signal=direction if score>=85 and direction!="WAIT" else "WAIT"
    rr=round(abs((tp1-entry)/(entry-sl)),2) if signal=="BUY" else round(abs((entry-tp1)/(sl-entry)),2) if signal=="SELL" else 0
    return {
        "signal":signal,"confidence":confidence,"score":score,"current_price":round(p5,4),
        "entry":round(entry,4) if direction!="WAIT" else None,
        "stop_loss":round(sl,4) if sl is not None else None,
        "take_profit":[round(tp1,4),round(tp2,4)] if tp1 is not None else [],
        "risk_reward":rr,"bias":bias,"draw_on_liquidity":sweep["type"],
        "premium_discount":pd,"m30":{"fvg":fvg30,"order_block":ob30,"atr":round(a30,4),"ema20":round(ema20,4),"ema50":round(ema50,4)},
        "m5":{"mss":mss5,"mss_level":mss_level,"displacement":disp5,"displacement_atr":round(disp_ratio,2),"fvg":fvg5,"atr":round(a5,4)},
        "liquidity":{"type":sweep["type"],"level":round(sweep["level"],4) if sweep["level"] else None,"extreme":round(sweep["extreme"],4) if sweep["extreme"] else None},
        "checks":checks,"reason":"; ".join(dict.fromkeys(reasons)) if reasons else "No ICT confluence",
        "model":"ICT M30 → M5","note":"85% is a confluence score, not a guaranteed win probability.",
        "evaluated_at":datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/v1/ict-signals/{symbol:path}")
async def get_ict_signals(symbol: str) -> dict[str, Any]:
    symbol=clean_symbol(symbol)
    try:
        c30,mode30,w30=await get_candles(symbol,"30min",260)
        c5,mode5,w5=await get_candles(symbol,"5min",260)
        result=build_ict_m30_m5(c30,c5)
        candle_time=c5[-2].get("time") if len(c5)>1 else c5[-1].get("time")
        result["ai_validation"] = None
        result["candle_time"]=candle_time
        return {"ok":True,"symbol":symbol,"mode":"live","source":"TradingView/OANDA canonical candle series",
                "m30_candles":len(c30),"m5_candles":len(c5),"warnings":[x for x in (w30,w5) if x],
                "ict":result,"generated_at":datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        return {"ok":False,"symbol":symbol,"mode":"error","error":str(exc),
                "ict":{"signal":"WAIT","confidence":0,"score":0,"reason":str(exc)}}


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
    """Auto-enter only ultra-conservative setups using confidence >=84.99%, strong zones, AI confirmation, and MTF alignment."""
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
        zone_quality = float(item.get("zone_quality") or 0)
        if direction not in ("BUY", "SELL") or confidence < AUTO_ENTRY_THRESHOLD or entry is None or sl is None or not tp:
            continue
        if zone_quality < AUTO_ENTRY_MIN_ZONE or item.get("quality_grade") not in {"A+","A"}:
            continue
        if ai_signal != direction or ai_agreement < AUTO_ENTRY_MIN_AI_AGREEMENT or ai_conf < AUTO_ENTRY_THRESHOLD or risk_flags:
            continue
        if AUTO_ENTRY_REQUIRE_MTF:
            tf_order=["1min","5min","15min","30min","1h","4h","1day"]
            idx=tf_order.index(tf) if tf in tf_order else -1
            higher=[result.get("timeframes",{}).get(x,{}) for x in tf_order[idx+1:]] if idx>=0 else []
            if higher and any(h.get("signal") != direction for h in higher):
                continue

        # AI is called only for a deterministic Auto Trading candidate that
        # already passed confidence, Strong Zone and MTF gates.
        candle_key = item.get("candle_time") or item.get("evaluated_at")
        ai_check = await ai_validate_module_signal("Auto Trading", key, tf, candle_key, item)
        item = merge_ai_validation(item, ai_check)
        direction = item.get("signal")
        confidence = float(item.get("confidence") or 0)
        ai_conf = float(ai_check.get("confidence") or 0)
        ai_agreement = float(ai_check.get("agreement") or 0)
        ai_signal = str(ai_check.get("signal") or "WAIT").upper()
        risk_flags = ai_check.get("risk_flags") if isinstance(ai_check.get("risk_flags"), list) else []
        if direction not in ("BUY","SELL") or confidence < AUTO_ENTRY_THRESHOLD:
            continue
        if ai_signal != direction or ai_agreement < AUTO_ENTRY_MIN_AI_AGREEMENT or ai_conf < AUTO_ENTRY_THRESHOLD or risk_flags:
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
            "ai_confidence": ai_conf,
            "ai_agreement": ai_agreement,
            "risk_reward": rr,
            "setup_strength": zone_quality,
            "setup_grade": "STRONG" if float(item.get("zone_quality") or confidence) >= 82 else "GOOD",
            "strong_setup": float(item.get("zone_quality") or confidence) >= 82,
            "entry_time": now.isoformat(),
        }
        if MT5_AUTO_TRADING:
            order_id = secrets.token_hex(8)
            MT5_ORDER_ATTEMPTS[order_id] = 0
            MT5_ORDER_QUEUE.append({"id": order_id, "symbol": key, "interval": tf, "direction": direction, "entry": float(entry), "sl": float(sl), "tp": [float(x) for x in tp], "volume": MT5_LOT_SIZE, "created_at": now.isoformat()})
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
    return {"enabled": True, "threshold": AUTO_ENTRY_THRESHOLD, "saved_timeframes": [x["interval"] for x in created], "trades": created, "count": len(created), "history_count": len(rows), "mode": "mt5_demo_queue" if MT5_AUTO_TRADING else "paper_auto_entry"}


MT5_CANDLE_MAX_AGE = int(os.getenv("MT5_CANDLE_MAX_AGE", "20"))
MT5_HEARTBEAT_TIMEOUT = int(os.getenv("MT5_HEARTBEAT_TIMEOUT", "30"))
MT5_TF_KEYS = {"1min":"1min","5min":"5min","15min":"15min","30min":"30min","1h":"1h","4h":"4h","1day":"1day"}

def _mt5_last_seen_age() -> float | None:
    raw = MT5_BRIDGE_STATE.get("last_seen")
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds())
    except Exception:
        return None

def _mt5_state_fresh() -> bool:
    if not MT5_BRIDGE_STATE.get("connected"):
        return False
    age = _mt5_last_seen_age()
    return age is not None and age <= MT5_CANDLE_MAX_AGE

def _mt5_is_connected_now() -> bool:
    if not MT5_BRIDGE_STATE.get("connected"):
        return False
    age = _mt5_last_seen_age()
    return age is not None and age <= MT5_HEARTBEAT_TIMEOUT

def _mt5_market_key(symbol: str | None) -> str:
    key = clean_symbol(symbol or MT5_BRIDGE_STATE.get("symbol") or DEFAULT_SYMBOL)
    if key in {"XAUUSD", "XAU/USD"}: return "XAU/USD"
    if key in {"EURUSD", "EUR/USD"}: return "EUR/USD"
    return key

def _mt5_market_state(symbol: str | None) -> dict[str, Any]:
    mk = _mt5_market_key(symbol)
    markets = MT5_BRIDGE_STATE.get("markets") or {}
    if mk in markets and isinstance(markets[mk], dict):
        return markets[mk]
    return MT5_BRIDGE_STATE

def get_mt5_candles(interval: str, limit: int = 320, symbol: str | None = None) -> list[dict[str, Any]]:
    market = _mt5_market_state(symbol)
    if not market.get("connected"):
        raise MarketDataError(f"Exness MT5 bridge {clean_symbol(symbol or DEFAULT_SYMBOL)} uchun ulanmagan")
    raw_seen = market.get("last_seen")
    try:
        age = max(0.0, (datetime.now(timezone.utc) - datetime.fromisoformat(str(raw_seen).replace("Z", "+00:00"))).total_seconds()) if raw_seen else None
    except Exception:
        age = None
    if age is None or age > MT5_CANDLE_MAX_AGE:
        raise MarketDataError(f"Exness MT5 {clean_symbol(symbol or DEFAULT_SYMBOL)} candle ma'lumoti eskirgan")
    key = MT5_TF_KEYS.get(validate_interval(interval), validate_interval(interval))
    rows = (market.get("candles") or {}).get(key) or []
    out=[]
    for c in rows:
        try:
            out.append({"time":int(c["time"]),"open":float(c["open"]),"high":float(c["high"]),"low":float(c["low"]),"close":float(c["close"])})
        except Exception:
            continue
    out.sort(key=lambda x:x["time"])
    return out[-max(2, min(limit, 500)):]

@app.get("/api/v1/trend-lines/{symbol:path}")
async def trend_lines(symbol: str, interval: str = DEFAULT_INTERVAL) -> dict[str, Any]:
    interval = validate_interval(interval)
    key = clean_symbol(symbol)
    try:
        candles_data = get_mt5_candles(interval, 320, key)
        closed = candles_data[:-1] if len(candles_data) > 1 else candles_data
        tl = _trendline_analysis(closed)
        fib = _fibonacci_analysis(closed)
        return {"symbol": key, "interval": interval, "candles": candles_data[-260:], "trendline": tl, "fibonacci": fib,
                "mode": "mt5", "warning": None, "provider": "Exness MT5", "source": f"MT5 {key} terminal candles",
                "generated_at": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        return {"symbol": key, "interval": interval, "candles": [],
                "trendline": {"available": False, "trend": "NEUTRAL", "type": "NONE", "touches": 0, "trend_power": 0, "breakout": "NO", "retest": "NO", "confirmation": "WAIT", "signal": "WAIT", "reason": str(exc)},
                "fibonacci": {"available": False, "direction": "NEUTRAL", "signal": "WAIT", "reason": str(exc), "levels": {}},
                "mode": "mt5_unavailable", "warning": str(exc), "provider": "Exness MT5",
                "generated_at": datetime.now(timezone.utc).isoformat()}

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
    row = SignalHistory(user_id=user.id, symbol=clean_symbol(symbol), interval=interval, direction=item["signal"], headline=f'{item["signal"]} • {item["setup"]}', price=float(item["entry"]), payload=json.dumps({"advanced":item,"setup":{"entry":item.get("entry"),"stop_loss":item.get("stop_loss"),"take_profit":item.get("take_profit",[])},"symbol":clean_symbol(symbol),"interval":interval,"source":"Signal Lab","candle_time":candles_data[-2].get("time") if len(candles_data)>1 else candles_data[-1].get("time")}), outcome="OPEN", created_at=datetime.now(timezone.utc), source="Signal Lab", candle_time=str(candles_data[-2].get("time") if len(candles_data)>1 else candles_data[-1].get("time")))
    session.add(row); session.commit(); session.refresh(row)
    return {"saved":True,"id":row.id,"signal":item}


def _setup_strength_from_payload(payload: dict[str, Any], confidence: float | None = None) -> tuple[float, str, bool]:
    """Extract a normalized setup strength for history without changing signal logic."""
    candidates: list[float] = []
    for key in ("setup_strength", "zone_strength", "zone_quality", "confidence_at_entry", "confidence"):
        v = payload.get(key)
        try:
            if v is not None: candidates.append(float(v))
        except (TypeError, ValueError):
            pass
    resp = payload.get("response") if isinstance(payload.get("response"), dict) else {}
    sig = payload.get("signal") if isinstance(payload.get("signal"), dict) else {}
    for obj in (resp, sig):
        for key in ("setup_strength", "zone_strength", "zone_quality", "confidence"):
            try:
                if obj.get(key) is not None: candidates.append(float(obj.get(key)))
            except (TypeError, ValueError):
                pass
    strength = max(candidates) if candidates else float(confidence or 0)
    # A signal already issued by the strong-zone engine is considered strong when
    # its confidence/zone quality is at least 82.  This is only a history label.
    label = "STRONG" if strength >= 82 else "GOOD" if strength >= 72 else "STANDARD"
    return round(strength, 2), label, strength >= 82


class MT5ConnectBody(BaseModel):
    login: str = ""
    server: str = ""
    password: str = ""
    demo: bool = True

class MT5LotBody(BaseModel):
    lot: float = 0.01

class MT5StateBody(BaseModel):
    connected: bool = False
    symbol: str = ""
    login: str = ""
    server: str = ""
    balance: float | None = None
    equity: float | None = None
    free_margin: float | None = None
    margin: float | None = None
    positions: int = 0
    error: str = ""
    candles: dict[str, list[dict[str, Any]]] = {}

class MT5ReportBody(BaseModel):
    action: str = ""
    ticket: str = ""
    symbol: str = ""
    status: str = ""
    price: float | None = None
    profit: float | None = None
    message: str = ""

class ModuleSignalBody(BaseModel):
    symbol: str = DEFAULT_SYMBOL
    interval: str = DEFAULT_INTERVAL
    source: str = "Signals"
    direction: str = "WAIT"
    confidence: float | None = None
    entry: float | None = None
    stop_loss: float | None = None
    take_profit: list[float] = Field(default_factory=list)
    headline: str = ""
    candle_time: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

@app.post("/api/v1/signals/record-module")
async def record_module_signal(body: ModuleSignalBody, authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    user = current_user(authorization, session)
    direction = str(body.direction or "WAIT").upper()
    source = str(body.source or "Signals")[:40]
    interval = validate_interval(body.interval)
    symbol = clean_symbol(body.symbol)
    if direction not in {"BUY", "SELL"}:
        return {"saved": False, "reason": "WAIT", "history_count": session.scalar(select(SignalHistory).where(SignalHistory.user_id == user.id).order_by(SignalHistory.id.desc()).limit(1).with_only_columns(SignalHistory.id)) or 0}
    # One record per module/timeframe/candle/direction. Refreshing the dashboard must not spam history.
    q = select(SignalHistory).where(
        SignalHistory.user_id == user.id,
        SignalHistory.source == source,
        SignalHistory.symbol == symbol,
        SignalHistory.interval == interval,
        SignalHistory.direction == direction,
        SignalHistory.candle_time == body.candle_time
    ).order_by(SignalHistory.id.desc())
    existing = session.scalar(q)
    if existing:
        return {"saved": False, "duplicate": True, "id": existing.id}
    payload = dict(body.payload or {})
    setup_strength, setup_grade, strong_setup = _setup_strength_from_payload(payload, body.confidence)
    payload.update({
        "source": source,
        "confidence_at_entry": body.confidence,
        "setup": {"entry": body.entry, "stop_loss": body.stop_loss, "take_profit": body.take_profit},
        "signal": {"direction": direction, "confidence": body.confidence},
        "candle_time": body.candle_time,
        "setup_strength": setup_strength,
        "setup_grade": setup_grade,
        "strong_setup": strong_setup,
    })
    row = SignalHistory(
        user_id=user.id, symbol=symbol, interval=interval, direction=direction,
        headline=(body.headline or f"{source} · {direction}")[:255],
        price=float(body.entry or 0), payload=json.dumps(payload, ensure_ascii=False),
        outcome="OPEN", created_at=datetime.now(timezone.utc),
        source=source, candle_time=body.candle_time
    )
    session.add(row); session.commit(); session.refresh(row)
    return {"saved": True, "id": row.id, "source": source, "outcome": row.outcome}

@app.get("/api/v1/signals/analytics")
async def signal_analytics(period: str = Query("all"), date: str | None = Query(None), authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    user = current_user(authorization, session)
    rows = await refresh_signal_outcomes(session, user.id)
    rows = filter_history_rows(rows, period, date)
    wins = sum(1 for r in rows if r.outcome == "TP HIT")
    losses = sum(1 for r in rows if r.outcome == "SL HIT")
    completed = wins + losses
    winrate = round((wins / completed) * 100, 2) if completed else 0.0
    by_tf: dict[str, dict[str, Any]] = {}
    by_source: dict[str, dict[str, Any]] = {}
    for r in rows:
        item = by_tf.setdefault(r.interval, {"total_signals":0,"completed_trades":0,"wins":0,"losses":0,"open":0,"ambiguous":0,"winrate":0.0})
        src = getattr(r, "source", None) or "Signals"
        src_item = by_source.setdefault(src, {"total_signals":0,"completed_trades":0,"wins":0,"losses":0,"open":0,"ambiguous":0,"winrate":0.0})
        src_item["total_signals"] += 1
        item["total_signals"] += 1
        if r.outcome == "TP HIT":
            item["wins"] += 1
            src_item["wins"] += 1
        elif r.outcome == "SL HIT":
            item["losses"] += 1
            src_item["losses"] += 1
        elif r.outcome == "AMBIGUOUS":
            item["ambiguous"] += 1
            src_item["ambiguous"] += 1
        elif r.outcome == "OPEN":
            item["open"] += 1
            src_item["open"] += 1
        item["completed_trades"] = item["wins"] + item["losses"]
        src_item["completed_trades"] = src_item["wins"] + src_item["losses"]
        item["winrate"] = round(item["wins"] / item["completed_trades"] * 100, 2) if item["completed_trades"] else 0.0
        src_item["winrate"] = round(src_item["wins"] / src_item["completed_trades"] * 100, 2) if src_item["completed_trades"] else 0.0
    return {"total_signals": len(rows), "completed_trades": completed, "wins": wins, "losses": losses, "winrate": winrate, "open": sum(1 for r in rows if r.outcome == "OPEN"), "ambiguous": sum(1 for r in rows if r.outcome == "AMBIGUOUS"), "by_timeframe": by_tf, "by_source": by_source}


@app.post("/api/v1/signals/save")
async def save_signal(symbol: str, interval: str = DEFAULT_INTERVAL, authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    user = current_user(authorization, session)
    analysis = await build_full_analysis(symbol, interval)
    item = SignalHistory(user_id=user.id, symbol=analysis["symbol"], interval=analysis["interval"], direction=analysis["direction"], headline=analysis["headline"], price=analysis["current_price"], payload=json.dumps({**analysis,"source":"Signals","candle_time":analysis.get("candle_time")}), outcome="OPEN", created_at=datetime.now(timezone.utc), source="Signals", candle_time=str(analysis.get("candle_time") or ""))
    session.add(item); session.commit(); session.refresh(item)
    return {"id": item.id, "status": "saved", "outcome": item.outcome}


@app.get("/api/v1/signals/history")
async def signal_history(limit: int = Query(50, ge=1, le=200), period: str = Query("all"), date: str | None = Query(None), authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    user = current_user(authorization, session)
    rows = await refresh_signal_outcomes(session, user.id, limit=200)
    rows = filter_history_rows(rows, period, date)
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
        setup_strength, setup_grade, strong_setup = _setup_strength_from_payload(payload, payload.get("confidence_at_entry", payload.get("signal",{}).get("confidence")))
        items.append({"id": r.id, "symbol": r.symbol, "interval": r.interval, "source": getattr(r, "source", None) or "Signals", "candle_time": getattr(r, "candle_time", None), "direction": r.direction, "entry": setup.get("entry", r.price), "tp": setup.get("take_profit", []), "sl": setup.get("stop_loss"), "headline": r.headline, "price": r.price, "outcome": r.outcome, "result_price": result.get("price"), "duration_seconds": duration_seconds, "duration_minutes": round(duration_seconds/60,2) if duration_seconds is not None else None, "auto_entry": bool(payload.get("auto_entry")), "confidence": payload.get("confidence_at_entry", payload.get("signal",{}).get("confidence")), "setup_strength": payload.get("setup_strength", setup_strength), "setup_grade": payload.get("setup_grade", setup_grade), "strong_setup": bool(payload.get("strong_setup", strong_setup)), "created_at": created_at.isoformat(), "closed_at": closed_at.isoformat() if closed_at else None})
    return {"items": items}


class AIControlBody(BaseModel):
    provider: str | None = None
    enabled: bool | None = None
    all_enabled: bool | None = None

@app.post("/api/v1/ai/providers/control")
async def ai_providers_control(body: AIControlBody):
    global AI_AUTO_MODE
    if body.all_enabled is not None:
        for p in list(AI_PROVIDER_ENABLED):
            AI_PROVIDER_ENABLED[p] = bool(body.all_enabled)
        AI_AUTO_MODE = bool(body.all_enabled)
        return {"ok":True,"auto_mode":AI_AUTO_MODE,"enabled":dict(AI_PROVIDER_ENABLED)}
    if body.provider:
        provider = body.provider.strip().lower()
        if provider not in AI_PROVIDER_ENABLED:
            raise HTTPException(status_code=404, detail="Unknown AI provider")
        AI_PROVIDER_ENABLED[provider] = (not AI_PROVIDER_ENABLED[provider]) if body.enabled is None else bool(body.enabled)
        return {"ok":True,"provider":provider,"enabled":AI_PROVIDER_ENABLED[provider],"auto_mode":AI_AUTO_MODE}
    raise HTTPException(status_code=400, detail="provider yoki all_enabled kerak")

@app.get("/api/v1/ai/providers")
async def ai_providers_status():
    # Only configured providers are exposed to the dashboard. Missing-key
    # providers are intentionally hidden instead of showing "OFFLINE".
    configured={
        "groq": bool(GROQ_API_KEY),
        "gemini": bool(GEMINI_API_KEY),
        "openrouter": bool(OPENROUTER_API_KEY),
        "groq_qwen": bool(GROQ_API_KEY),
        "mistral": bool(MISTRAL_API_KEY),
        "cerebras": bool(CEREBRAS_API_KEY),
        "cloudflare": bool(CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN),
        "deepseek": bool(DEEPSEEK_API_KEY),
        "openai": bool(OPENAI_API_KEY),
        "huggingface": bool(HF_TOKEN),
    }
    models={"groq":GROQ_MODEL,"gemini":GEMINI_MODEL,"openrouter":OPENROUTER_MODEL,"groq_qwen":GROQ_QWEN_MODEL,"mistral":MISTRAL_MODEL,"cerebras":CEREBRAS_MODEL,"cloudflare":CLOUDFLARE_MODEL,"deepseek":DEEPSEEK_MODEL,"openai":OPENAI_MODEL,"huggingface":HF_MODEL}
    providers=[]
    now_mono = asyncio.get_running_loop().time()
    def display_score(p: str) -> float:
        prof=AI_PROVIDER_PROFILE.get(p, {"quality":70,"speed":70,"capacity":60,"cost":60})
        base=prof["quality"]*0.40 + prof["speed"]*0.20 + prof["capacity"]*0.25 + prof["cost"]*0.15
        st=AI_PROVIDER_STATUS.get(p) or {}
        status=st.get("status") or "READY"
        if status == "ONLINE": base += 8
        elif status == "LIMITED": base -= 18
        if AI_PROVIDER_COOLDOWN_UNTIL.get(p,0.0)>now_mono: base -= 35
        return round(base,1)
    configured_ids=[p for p in AI_FALLBACK_ORDER if p in configured and configured[p]]
    for p in sorted(configured_ids, key=display_score, reverse=True):
        st=AI_PROVIDER_STATUS.get(p) or {}
        status=st.get("status") or "READY"
        error=(st.get("error") or "").strip()
        if status == "ONLINE":
            reason="AI so‘rovi muvaffaqiyatli bajarildi."
        elif status == "LIMITED":
            reason=error or "Rate limit/quota vaqtincha cheklangan."
        elif status == "OFFLINE":
            reason=error or "Provider javob bermadi yoki API xatosi."
        else:
            reason="Hali real AI so‘rovi bilan tekshirilmagan."
        prof=AI_PROVIDER_PROFILE.get(p,{"quality":70,"speed":70,"capacity":60,"cost":60})
        providers.append({"id":p,"configured":True,"enabled":AI_PROVIDER_ENABLED.get(p,True),"status":("OFF" if not AI_PROVIDER_ENABLED.get(p,True) else status),"model":models[p],"reason":("Qo‘lda o‘chirilgan — router bu AI'ni chaqirmaydi." if not AI_PROVIDER_ENABLED.get(p,True) else reason),"error":error,"http_status":st.get("http_status"),"checked_at":st.get("checked_at"),"score":display_score(p),"quality":prof["quality"],"speed":prof["speed"],"capacity":prof["capacity"],"cost":prof["cost"]})
    return {"order":[x["id"] for x in providers],"router":"score","providers":providers}

@app.get("/api/v1/mt5/status")
async def mt5_status(symbol: str = DEFAULT_SYMBOL, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    key = _mt5_market_key(symbol)
    state = dict(_mt5_market_state(key))
    raw_seen = state.get("last_seen")
    try:
        age = max(0.0, (datetime.now(timezone.utc) - datetime.fromisoformat(str(raw_seen).replace("Z", "+00:00"))).total_seconds()) if raw_seen else None
    except Exception:
        age = None
    connected_now = bool(state.get("connected")) and age is not None and age <= MT5_HEARTBEAT_TIMEOUT
    state["connected"] = connected_now
    state["heartbeat_age_sec"] = round(age, 1) if age is not None else None
    state["connection_state"] = "CONNECTED" if connected_now else ("STALE" if age is not None and age <= 60 else "DISCONNECTED")
    return {"ok": True, "symbol": key, "auto_trading": MT5_AUTO_TRADING, "lot": MT5_LOT_SIZE, "state": state, "queue": len(MT5_ORDER_QUEUE), "demo_only": True, "heartbeat_timeout_sec": MT5_HEARTBEAT_TIMEOUT}

@app.post("/api/v1/mt5/connect")
async def mt5_connect(body: MT5ConnectBody, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not body.demo:
        raise HTTPException(status_code=400, detail="Faqat DEMO hisob ulanishi mumkin.")
    if not body.login or not body.server or not body.password:
        raise HTTPException(status_code=400, detail="MT5 Login, Server va Trading Password kiriting.")
    # Credentials are intentionally NOT persisted. The actual broker login is performed by MT5 terminal/EA.
    MT5_BRIDGE_STATE.update({"login": body.login, "server": body.server, "connected": False, "last_error": "MT5 terminal/EA bridge hali ulanmagan."})
    return {"ok": True, "demo_only": True, "connected": False, "message": "Ma'lumotlar qabul qilindi. Exness DEMO MT5 terminalida EA/bridge ishga tushirilgach ulanish tasdiqlanadi."}

@app.post("/api/v1/mt5/lot")
async def mt5_lot(body: MT5LotBody, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    global MT5_LOT_SIZE
    lot = float(body.lot)
    if not (0.01 <= lot <= 100.0):
        raise HTTPException(status_code=400, detail="Lot 0.01 dan 100 gacha bo‘lishi kerak.")
    # Normalize to two decimals for common MT5 lot steps.
    MT5_LOT_SIZE = round(lot, 2)
    return {"ok": True, "lot": MT5_LOT_SIZE, "demo_only": True}

@app.post("/api/v1/mt5/auto-trading")
async def mt5_auto_trading(enabled: bool = Query(...), authorization: str | None = Header(default=None)) -> dict[str, Any]:
    global MT5_AUTO_TRADING
    MT5_AUTO_TRADING = bool(enabled)
    return {"ok": True, "auto_trading": MT5_AUTO_TRADING, "demo_only": True}

@app.get("/api/v1/mt5/poll")
async def mt5_poll(token: str = Query(...)) -> dict[str, Any]:
    if not secrets.compare_digest(token, MT5_BRIDGE_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid MT5 bridge token")
    MT5_BRIDGE_STATE["last_seen"] = datetime.now(timezone.utc).isoformat()
    if not MT5_AUTO_TRADING or not MT5_ORDER_QUEUE:
        return {"ok": True, "orders": []}
    # Claim a small batch without deleting it. The EA reports success/failure; failed
    # orders are re-queued up to three times so a transient MT5/WebRequest error does
    # not silently lose a signal.
    orders = []
    for item in MT5_ORDER_QUEUE:
        if item.get("claimed"):
            continue
        item["claimed"] = True
        MT5_ORDER_ATTEMPTS[item["id"]] = MT5_ORDER_ATTEMPTS.get(item["id"], 0) + 1
        orders.append(item)
        if len(orders) >= 10:
            break
    return {"ok": True, "orders": orders}

@app.post("/api/v1/mt5/state")
async def mt5_state(body: MT5StateBody, token: str = Query(...)) -> dict[str, Any]:
    if not secrets.compare_digest(token, MT5_BRIDGE_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid MT5 bridge token")
    now_iso = datetime.now(timezone.utc).isoformat()
    key = _mt5_market_key(body.symbol or MT5_BRIDGE_STATE.get("symbol") or DEFAULT_SYMBOL)
    snapshot = {"connected": body.connected, "account": body.login or None, "server": body.server or None, "balance": body.balance, "equity": body.equity, "free_margin": body.free_margin, "margin": body.margin, "positions": body.positions, "last_seen": now_iso, "last_error": body.error or "", "symbol": key, "candles": body.candles or {}}
    MT5_BRIDGE_STATE.update(snapshot)
    MT5_BRIDGE_STATE.setdefault("markets", {})[key] = snapshot
    return {"ok": True, "symbol": key}

@app.post("/api/v1/mt5/report")
async def mt5_report(body: MT5ReportBody, token: str = Query(...)) -> dict[str, Any]:
    if not secrets.compare_digest(token, MT5_BRIDGE_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid MT5 bridge token")
    MT5_BRIDGE_STATE["last_seen"] = datetime.now(timezone.utc).isoformat()
    status = body.status.lower()
    if status in {"error", "failed", "order_failed"}:
        MT5_BRIDGE_STATE["last_error"] = body.message
    # Finalize a claimed queue item using the EA's order id. Successful orders are
    # removed; failed orders are released for a limited retry count.
    if body.ticket:
        for idx, item in enumerate(list(MT5_ORDER_QUEUE)):
            if str(item.get("id")) != str(body.ticket):
                continue
            if status in {"order_sent", "sent", "success", "filled"}:
                MT5_ORDER_QUEUE.pop(idx)
                MT5_ORDER_ATTEMPTS.pop(str(body.ticket), None)
            elif status in {"error", "failed", "order_failed"}:
                attempts = MT5_ORDER_ATTEMPTS.get(str(body.ticket), 1)
                if attempts >= 3:
                    MT5_ORDER_QUEUE.pop(idx)
                    MT5_ORDER_ATTEMPTS.pop(str(body.ticket), None)
                else:
                    item["claimed"] = False
            break
    return {"ok": True, "queue": len(MT5_ORDER_QUEUE)}

@app.get("/api/health")
async def api_health() -> dict[str, Any]:
    return {"ok": True, "service": "xauusd-trading", "timestamp": datetime.now(timezone.utc).isoformat()}

@app.get("/eurusd")
@app.get("/eurusd/")
@app.get("/EURUSD")
@app.get("/EURUSD/")
async def read_eurusd() -> FileResponse:
    return FileResponse(os.path.join(BASE_DIR, "eurusd.html"))

@app.get("/")
async def read_root() -> FileResponse:
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

# Persistent signal-history diagnostics.
@app.get("/api/v1/signals/storage")
async def signal_storage_status(authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    user = current_user(authorization, session)
    try:
        total = session.scalar(select(func.count()).select_from(SignalHistory).where(SignalHistory.user_id == user.id)) or 0
    except Exception:
        total = 0
    backend = "postgresql" if DATABASE_URL.startswith("postgresql") else "sqlite"
    return {
        "ok": True,
        "backend": backend,
        "persistent_across_railway_redeploy": backend == "postgresql",
        "signal_history_rows": int(total),
        "note": "Signal snapshots are stored in signal_history.payload. Use Railway PostgreSQL DATABASE_URL for persistence across redeploys."
    }
