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
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi import WebSocket, WebSocketDisconnect
from pattern_engine import detect_patterns
from msai_strategy import analyze_msai, summarize_mtf, direction_from_candles, aggregate_weekly
from smc_strategy import analyze_smc, summarize_smc_mtf
from algo_smc_strategy import analyze_algo_smc
from trend_channel_strategy import analyze_trend_channel
from fibonacci_strategy import analyze_fibonacci
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, create_engine, select, func, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

load_dotenv()

APP_TITLE = os.getenv("APP_TITLE", "Trading SaaS Analytics Platform")
MARKET_PROVIDER = os.getenv("MARKET_PROVIDER", "auto").lower()
# Shared market-data router: a preferred provider is only the first attempt.
# Every module uses the same symbol/timeframe snapshot and automatically falls
# through to the next available provider when the current provider fails.
_DEFAULT_MARKET_FALLBACK_ORDER = ["tradingview", "realmarketapi", "twelvedata", "yahoo"]
_raw_market_order = [x.strip().lower() for x in os.getenv("MARKET_FALLBACK_ORDER", "").split(",") if x.strip()]
MARKET_FALLBACK_ORDER: list[str] = []
for _market_provider_name in (_raw_market_order + _DEFAULT_MARKET_FALLBACK_ORDER):
    if _market_provider_name not in MARKET_FALLBACK_ORDER:
        MARKET_FALLBACK_ORDER.append(_market_provider_name)
MARKET_PROVIDER_COOLDOWN_SECONDS = max(3, int(os.getenv("MARKET_PROVIDER_COOLDOWN_SECONDS", "20")))
MARKET_PROVIDER_COOLDOWN_UNTIL: dict[str, float] = {}
MARKET_PROVIDER_STATUS: dict[str, dict[str, Any]] = {}
REALMARKET_API_KEY = os.getenv("REALMARKET_API_KEY", "").strip()
REALMARKET_API_BASE = os.getenv("REALMARKET_API_BASE", "https://api.realmarketapi.com").strip().rstrip("/")
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "").strip()
TRADING_ECONOMICS_API_KEY = os.getenv("TRADING_ECONOMICS_API_KEY", "").strip()
CALENDAR_PROVIDER = os.getenv("CALENDAR_PROVIDER", "auto").strip().lower()
FOREX_FACTORY_CALENDAR_URL = os.getenv("FOREX_FACTORY_CALENDAR_URL", "https://www.forexfactory.com/calendar?export=csv&week=this").strip()
def _clean_env_secret(name: str, *aliases: str) -> str:
    """Read Railway secrets robustly; trim accidental quotes/Bearer prefix."""
    for key in (name, *aliases):
        value = (os.getenv(key, "") or "").strip()
        if value.startswith(("\"", "'")) and value.endswith(value[0]) and len(value) >= 2:
            value = value[1:-1].strip()
        if value.lower().startswith("bearer "):
            value = value[7:].strip()
        if value:
            return value
    return ""

OPENAI_API_KEY = _clean_env_secret("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-sol").strip() or "gpt-5.6-sol"
ANTHROPIC_API_KEY = _clean_env_secret("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-fable-5").strip() or "claude-fable-5"
ANTHROPIC_MODEL_2 = os.getenv("ANTHROPIC_MODEL_2", "claude-opus-5").strip() or "claude-opus-5"
ANTHROPIC_MODEL_3 = os.getenv("ANTHROPIC_MODEL_3", "claude-sonnet-5").strip() or "claude-sonnet-5"
HF_TOKEN = _clean_env_secret("HUGGINGFACE_API_KEY", "HF_TOKEN")
HF_MODEL = (
    os.getenv("HUGGINGFACE_MODEL", "").strip()
    or os.getenv("HF_MODEL", "").strip()
    or "Qwen/Qwen3-32B"
)
GROQ_API_KEY = _clean_env_secret("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip() or "openai/gpt-oss-120b"
GROQ_API_KEY_2 = _clean_env_secret("GROQ_API_KEY_2", "GROQ2_API_KEY")
GROQ_MODEL_2 = (
    os.getenv("GROQ_MODEL_2", "qwen/qwen3.8-27b").strip()
    or os.getenv("GROQ2_MODEL", "qwen/qwen3.8-27b").strip()
    or "qwen/qwen3.8-27b"
)
GEMINI_API_KEY = _clean_env_secret("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip() or "gemini-3.8-flash"
OPENROUTER_API_KEY = _clean_env_secret("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free").strip() or "openrouter/free"
MISTRAL_API_KEY = _clean_env_secret("MISTRAL_API_KEY")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest").strip() or "mistral-small-latest"
CEREBRAS_API_KEY = _clean_env_secret("CEREBRAS_API_KEY")
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
# SignalX uses a FREE-FIRST / PAID-LAST policy.
# Free/low-cost providers are exhausted before the paid emergency provider is used.
# The order can still be overridden with AI_FALLBACK_ORDER in Railway.
_DEFAULT_AI_FREE_FIRST_ORDER = [
    "groq",        # GPT-OSS 120B free tier
    "groq_2",      # Qwen free tier
    "gemini",      # Gemini Flash free tier (when enabled on the API key)
    "cerebras",    # Cerebras free tier / account quota
    "mistral",     # Mistral free/experiment quota where available
    "cloudflare",  # Cloudflare AI quota where configured
    "huggingface", # HF included credits / provider quota
    "openrouter",  # OpenRouter free-model pool (request-limited)
]
_DEFAULT_AI_PAID_FALLBACK_ORDER = [
    "deepseek",    # emergency low-cost paid fallback
    "anthropic", "anthropic_2", "anthropic_3",
    "openai",
]
_DEFAULT_AI_FALLBACK_ORDER = _DEFAULT_AI_FREE_FIRST_ORDER + _DEFAULT_AI_PAID_FALLBACK_ORDER
_raw_ai_order = [x.strip().lower() for x in os.getenv("AI_FALLBACK_ORDER", "").split(",") if x.strip()]
AI_FALLBACK_ORDER: list[str] = []
for _provider_name in (_raw_ai_order + _DEFAULT_AI_FALLBACK_ORDER):
    if _provider_name not in AI_FALLBACK_ORDER:
        AI_FALLBACK_ORDER.append(_provider_name)
AI_ROUTER_MODE = os.getenv("AI_ROUTER_MODE", "order").strip().lower() or "order"
AI_PAID_FALLBACK_ENABLED = os.getenv("AI_PAID_FALLBACK_ENABLED", "true").strip().lower() == "true"
AI_PAID_PROVIDER_IDS = {"deepseek", "anthropic", "anthropic_2", "anthropic_3", "openai"}
# Provider profile: quality, speed, capacity/limits, cost-efficiency (0-100).
# These are routing heuristics, not provider guarantees; live status is weighted dynamically.
AI_PROVIDER_PROFILE = {
    "groq": {"quality": 95, "speed": 99, "capacity": 78, "cost": 94},
    "groq_2": {"quality": 90, "speed": 99, "capacity": 82, "cost": 96},
    "deepseek": {"quality": 96, "speed": 88, "capacity": 99, "cost": 97},
    "gemini": {"quality": 94, "speed": 91, "capacity": 88, "cost": 88},
    "anthropic": {"quality": 97, "speed": 88, "capacity": 84, "cost": 82},
    "anthropic_2": {"quality": 99, "speed": 84, "capacity": 82, "cost": 72},
    "anthropic_3": {"quality": 98, "speed": 90, "capacity": 86, "cost": 80},
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
# Live AI results can be cached for the candle; provider-failure fallbacks use a short
# cache so a recovered provider can be used without waiting for a new candle.
AI_FAILURE_CACHE_TTL = max(5, int(os.getenv("AI_FAILURE_CACHE_TTL", "20")))
AI_PROVIDER_COOLDOWN_SECONDS = int(os.getenv("AI_PROVIDER_COOLDOWN_SECONDS", "120"))
AI_PROVIDER_COOLDOWN_UNTIL: dict[str, float] = {}

AI_PROVIDER_STATUS: dict[str, dict[str, Any]] = {}
# Runtime AI controls. OFF providers are never called by the router.
AI_PROVIDER_ENABLED: dict[str, bool] = {
    "groq": True, "groq_2": True, "deepseek": True, "gemini": True,
    "anthropic": True, "anthropic_2": True, "anthropic_3": True,
    "openai": True, "mistral": True, "cerebras": True, "cloudflare": True,
    "huggingface": True, "openrouter": True,
}
AI_AUTO_MODE = True
AI_SIGNAL_CONFIRM_ONLY = os.getenv("AI_SIGNAL_CONFIRM_ONLY", "true").lower() == "true"

# AI Q&A is a user-facing conversational layer. It reuses the existing AI fallback
# network and current market/calendar context, while keeping a small per-user
# rate limit so one browser session cannot exhaust provider quotas.
AI_QA_MAX_REQUESTS = max(1, int(os.getenv("AI_QA_MAX_REQUESTS", "12")))
AI_QA_WINDOW_SECONDS = max(60, int(os.getenv("AI_QA_WINDOW_SECONDS", "300")))
AI_QA_RATE: dict[int, list[float]] = {}

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
    """Call OpenAI-compatible providers with an explicit Authorization header."""
    key = _clean_env_secret_value(api_key)
    if not key:
        raise RuntimeError(f"{provider}: API key is missing")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update({k: v for k, v in extra_headers.items() if v})
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    url = base_url.rstrip("/") + "/chat/completions"
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code >= 400:
            # A few compatible APIs reject response_format; retry once without it.
            if response.status_code in (400, 404, 422) and "response_format" in response.text.lower():
                payload.pop("response_format", None)
                response = await client.post(url, headers=headers, json=payload)
            if response.status_code >= 400:
                try:
                    body = response.json()
                except Exception:
                    body = {"message": response.text[:500]}
                exc = RuntimeError(str(body.get("error") or body.get("message") or body))
                exc.status_code = response.status_code
                exc.body = body
                raise exc
        try:
            data = response.json()
        except Exception as exc:
            raise RuntimeError(f"{provider}: non-JSON HTTP response") from exc
        choices = data.get("choices") or []
        message = choices[0].get("message") if choices else None
        text = ""
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                text = content.strip()
            elif isinstance(content, list):
                text = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict)).strip()
        text = text or str(data.get("output_text") or "").strip()
        if not text:
            raise RuntimeError(f"{provider}: empty response")
        return text, provider

def _clean_env_secret_value(value: str) -> str:
    value = str(value or "").strip()
    if value.startswith(("\"", "'")) and value.endswith(value[0]) and len(value) >= 2:
        value = value[1:-1].strip()
    if value.lower().startswith("bearer "):
        value = value[7:].strip()
    return value

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
    if provider == "groq_2" and GROQ_API_KEY_2:
        return await _openai_compatible_completion(GROQ_API_KEY_2, "https://api.groq.com/openai/v1", GROQ_MODEL_2, prompt, "groq_2")
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
    if provider in {"anthropic", "anthropic_2", "anthropic_3"} and ANTHROPIC_API_KEY:
        model = {
            "anthropic": ANTHROPIC_MODEL,
            "anthropic_2": ANTHROPIC_MODEL_2,
            "anthropic_3": ANTHROPIC_MODEL_3,
        }[provider]
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": 1600,
            "temperature": 0.1,
            "system": "Return exactly one valid JSON object. No markdown fences, no commentary outside JSON.",
            "messages": [{"role": "user", "content": prompt}],
        }
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            r = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
            if r.status_code >= 400:
                try:
                    detail = r.json()
                except Exception:
                    detail = r.text[:800]
                exc = RuntimeError(f"Anthropic HTTP {r.status_code}: {detail}")
                setattr(exc, "status_code", r.status_code)
                setattr(exc, "body", detail if isinstance(detail, dict) else {"message": str(detail)})
                raise exc
            data = r.json()
        content = data.get("content") or []
        text = "".join(str(item.get("text", "")) for item in content if isinstance(item, dict) and item.get("type") == "text").strip()
        if not text:
            raise RuntimeError(f"{provider}: empty response")
        return text, provider
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

def _ai_qa_rate_ok(user_id: int) -> tuple[bool, int]:
    now = datetime.now(timezone.utc).timestamp()
    recent = [t for t in AI_QA_RATE.get(user_id, []) if now - t < AI_QA_WINDOW_SECONDS]
    if len(recent) >= AI_QA_MAX_REQUESTS:
        retry = max(1, int(AI_QA_WINDOW_SECONDS - (now - recent[0])))
        AI_QA_RATE[user_id] = recent
        return False, retry
    recent.append(now)
    AI_QA_RATE[user_id] = recent
    return True, 0


def _ai_qa_extract_answer(raw: str) -> dict[str, Any]:
    """Parse the provider JSON while tolerating plain-text fallback responses."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("AI returned an empty response")
    candidates = [text]
    if "```" in text:
        candidates.append(re.sub(r"^```(?:json)?|```$", "", text, flags=re.I | re.M).strip())
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        candidates.append(text[start:end+1])
    for cand in candidates:
        try:
            data = json.loads(cand)
            if isinstance(data, dict):
                answer = str(data.get("answer") or data.get("response") or "").strip()
                if answer:
                    return {
                        "answer": answer,
                        "bias": str(data.get("bias") or "NEUTRAL").upper(),
                        "confidence": float(data.get("confidence") or 0),
                        "risk_note": str(data.get("risk_note") or "").strip(),
                    }
        except Exception:
            continue
    return {"answer": text, "bias": "NEUTRAL", "confidence": 0.0, "risk_note": ""}


async def _ai_qa_calendar_context(days: int = 7) -> dict[str, Any]:
    """Best-effort economic-event context for AI Q&A; never fabricates events."""
    providers = []
    if TRADING_ECONOMICS_API_KEY:
        providers.append(lambda: _calendar_tradingeconomics(days))
    if FINNHUB_API_KEY:
        providers.append(lambda: _calendar_finnhub(days))
    # Forex Factory endpoint can work without a key, so keep it as the final fallback.
    providers.append(lambda: _calendar_forexfactory(days))
    for fn in providers:
        try:
            data = await fn()
            events = data.get("events") or []
            if events:
                return {"provider": data.get("provider"), "events": events[:80], "warning": data.get("warning")}
        except Exception:
            continue
    return {"provider": None, "events": [], "warning": "Live economic event source unavailable."}


async def build_ai_qa_context(symbol: str, interval: str) -> dict[str, Any]:
    symbol = clean_symbol(symbol)
    interval = validate_interval(interval)
    now = datetime.now(timezone.utc)
    async def safe_call(coro, default, timeout_seconds=7):
        try:
            return await asyncio.wait_for(coro, timeout=timeout_seconds)
        except Exception:
            return default

    quote_task = safe_call(fetch_live_price_any(symbol, interval), (None, None), 6)
    analysis_task = safe_call(build_full_analysis(symbol, interval), {}, 8)
    mtf_task = safe_call(multi_timeframe(symbol), {"overall": "UNAVAILABLE", "timeframes": {}}, 8)
    cal_task = safe_call(_ai_qa_calendar_context(7), {"provider": None, "events": [], "warning": "Live economic event source unavailable."}, 6)
    quote_result, analysis, mtf, cal = await asyncio.gather(quote_task, analysis_task, mtf_task, cal_task)

    price = None
    quote_source = None
    if not isinstance(quote_result, Exception):
        try:
            price, quote_source = float(quote_result[0]), quote_result[1]
        except Exception:
            pass
    if isinstance(analysis, Exception):
        analysis = {}
    if isinstance(mtf, Exception):
        mtf = {"overall": "UNAVAILABLE", "timeframes": {}}
    if isinstance(cal, Exception):
        cal = {"provider": None, "events": [], "warning": str(cal)}

    # Keep only compact, model-relevant fields; never send secrets/API credentials.
    events = []
    for ev in (cal.get("events") or [])[:60]:
        events.append({
            "time": ev.get("time"), "country": ev.get("country"), "event": ev.get("event"),
            "impact": ev.get("impact"), "forecast": ev.get("forecast") or ev.get("estimate"),
            "previous": ev.get("previous"), "actual": ev.get("actual"), "source": ev.get("source"),
        })
    return {
        "as_of_utc": now.isoformat(),
        "timezone": "Asia/Tashkent",
        "symbol": symbol,
        "interval": interval,
        "current_price": price,
        "quote_source": quote_source,
        "analysis": {
            "direction": analysis.get("direction"),
            "current_price": analysis.get("current_price"),
            "technical": analysis.get("technical"),
            "levels": analysis.get("levels"),
            "setup": analysis.get("setup"),
            "multi_timeframe": analysis.get("multi_timeframe"),
        },
        "mtf": {
            "overall": mtf.get("overall"),
            "available_count": mtf.get("available_count"),
            "bullish_count": mtf.get("bullish_count"),
            "bearish_count": mtf.get("bearish_count"),
            "timeframes": mtf.get("timeframes") or {},
        },
        "economic_calendar": {
            "provider": cal.get("provider"),
            "events": events,
            "warning": cal.get("warning"),
        },
    }

def _extract_json_object(raw: str) -> dict[str, Any]:
    """Parse provider JSON while tolerating markdown fences and surrounding prose."""
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("provider returned non-JSON content")
        value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("provider JSON must be an object")
    return value


def _dedupe_provider_order(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        name = str(value or "").strip().lower()
        if name and name in AI_PROVIDER_ENABLED and name not in out:
            out.append(name)
    return out


async def ai_json_completion(prompt: str) -> tuple[str, str]:
    """Shared multi-provider AI router used by every AI-assisted module.

    A module never depends on a single provider. The router prefers healthy/available
    providers, applies per-provider cooldowns, and immediately advances to the next
    configured provider on rate-limit, auth, model, network, timeout, or invalid-JSON
    failures. The final caller may then use its own deterministic fallback.
    """
    configured = {
        "groq": bool(GROQ_API_KEY),
        "groq_2": bool(GROQ_API_KEY_2),
        "gemini": bool(GEMINI_API_KEY),
        "anthropic": bool(ANTHROPIC_API_KEY),
        "anthropic_2": bool(ANTHROPIC_API_KEY),
        "anthropic_3": bool(ANTHROPIC_API_KEY),
        "openrouter": bool(OPENROUTER_API_KEY),
        "mistral": bool(MISTRAL_API_KEY),
        "cerebras": bool(CEREBRAS_API_KEY),
        "cloudflare": bool(CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN),
        "deepseek": bool(DEEPSEEK_API_KEY),
        "openai": bool(OPENAI_API_KEY),
        "huggingface": bool(HF_TOKEN),
    }

    # Even when AI_PROVIDER is explicitly set, it is only the preferred provider.
    # All other configured providers remain eligible as automatic fallbacks.
    preferred = [AI_PROVIDER] if AI_PROVIDER not in {"auto", ""} else []
    raw_order = _dedupe_provider_order(preferred + AI_FALLBACK_ORDER)
    candidates = [p for p in raw_order if configured.get(p, False) and AI_PROVIDER_ENABLED.get(p, True)]
    if not AI_PAID_FALLBACK_ENABLED:
        candidates = [p for p in candidates if p not in AI_PAID_PROVIDER_IDS]
    if not candidates:
        raise RuntimeError("No configured AI providers are available")

    errors: list[str] = []
    now_mono = asyncio.get_running_loop().time()

    def route_score(provider: str) -> float:
        prof = AI_PROVIDER_PROFILE.get(provider, {"quality": 70, "speed": 70, "capacity": 60, "cost": 60})
        base = (prof["quality"] * 0.40 + prof["speed"] * 0.20 + prof["capacity"] * 0.25 + prof["cost"] * 0.15)
        st = AI_PROVIDER_STATUS.get(provider) or {}
        status = st.get("status")
        if status == "ONLINE":
            base += 18
        elif status == "LIMITED":
            base -= 30
        elif status == "OFFLINE":
            base -= 12
        if AI_PROVIDER_COOLDOWN_UNTIL.get(provider, 0.0) > now_mono:
            base -= 80
        return round(base, 2)

    order = sorted(candidates, key=route_score, reverse=True) if AI_ROUTER_MODE == "score" else candidates

    for provider in order:
        cooldown_until = AI_PROVIDER_COOLDOWN_UNTIL.get(provider, 0.0)
        if cooldown_until > now_mono:
            remaining = max(1, int(cooldown_until - now_mono))
            AI_PROVIDER_STATUS[provider] = {
                "status": "LIMITED",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "error": f"provider cooldown ({remaining}s remaining)",
            }
            errors.append(f"{provider}: cooldown")
            continue

        try:
            text, used = await _provider_call(provider, prompt)
            # Every current AI-assisted feature requests strict JSON. Validate it here
            # so malformed output from one provider cannot block the rest of the network.
            _extract_json_object(text)
            AI_PROVIDER_STATUS[used] = {
                "status": "ONLINE",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "last_success_at": datetime.now(timezone.utc).isoformat(),
                "error": "",
            }
            AI_PROVIDER_COOLDOWN_UNTIL.pop(used, None)
            return text, used
        except Exception as exc:
            msg, http_status = _provider_error_details(exc)
            low = msg.lower()
            invalid_json = "non-json" in low or "json" in low and "provider returned" in low
            limited = http_status == 429 or "rate limit" in low or "rate_limit" in low or "quota" in low or "too many requests" in low
            if limited or invalid_json:
                AI_PROVIDER_COOLDOWN_UNTIL[provider] = now_mono + AI_PROVIDER_COOLDOWN_SECONDS
            AI_PROVIDER_STATUS[provider] = {
                "status": "LIMITED" if limited else "OFFLINE",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "error": msg[:360],
                "http_status": http_status,
            }
            errors.append(f"{provider}: {msg[:180]}")
            continue

    raise RuntimeError("All configured AI providers failed: " + " | ".join(errors))


CANDLE_LIMIT = max(50, min(int(os.getenv("CANDLE_LIMIT", "220")), 500))
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "12"))
NODE_MARKET_URL = os.getenv("NODE_MARKET_URL", "http://127.0.0.1:3001").strip().rstrip("/")
TRADINGVIEW_SYMBOL = os.getenv("TRADINGVIEW_SYMBOL", "OANDA:XAUUSD").strip() or "OANDA:XAUUSD"
TRADINGVIEW_WS_URL = os.getenv("TRADINGVIEW_WS_URL", "wss://data.tradingview.com/socket.io/websocket").strip()
TRADINGVIEW_BARS = max(80, min(int(os.getenv("TRADINGVIEW_BARS", "260")), 500))
TRADINGVIEW_TIMEOUT = float(os.getenv("TRADINGVIEW_TIMEOUT", "10"))
MT5_BRIDGE_TOKEN = os.getenv("MT5_BRIDGE_TOKEN", "change-this-mt5-bridge-token").strip()
MT5_AUTO_TRADING = os.getenv("MT5_AUTO_TRADING", "true").lower() == "true"
AUTOTRADE_INTERNAL_TOKEN = os.getenv("AUTOTRADE_INTERNAL_TOKEN", "").strip() or secrets.token_urlsafe(32)
MT5_LOT_SIZE = float(os.getenv("MT5_DEFAULT_LOT", "0.01"))
MT5_BRIDGE_STATE: dict[str, Any] = {"connected": False, "account": None, "server": None, "balance": None, "equity": None, "free_margin": None, "margin": None, "positions": 0, "last_seen": None, "last_error": "", "symbol": None, "candles": {}, "markets": {}}
MT5_ORDER_QUEUE: list[dict[str, Any]] = []
# Prevent re-queuing the same XAU/USD source/timeframe/candle/direction after a successful fill.
MT5_EXECUTED_KEYS: set[tuple[str, str, str, str, str]] = set()

# Signal History is the persisted source-of-truth for new AutoTrade forwarding.
# Only records created after this process started are eligible for the bridge scan;
# this prevents a deployment/restart from replaying old historical signals.
_HISTORY_AUTOTRADE_BRIDGE_STARTED_AT = datetime.now(timezone.utc)

def _history_row_levels_for_autotrade(row: "SignalHistory", payload: dict[str, Any]) -> tuple[float | None, float | None, list[float]]:
    entry, sl, tp1, tp2 = _history_numeric_levels(payload, row)
    tps = [x for x in (tp1, tp2) if x is not None and float(x) > 0]
    return entry, sl, tps

def _forward_recent_history_to_mt5(session: Session, user_id: int) -> list[dict[str, Any]]:
    """Forward newly-created eligible History records into the existing MT5 queue exactly once.

    History creation remains independent from execution, but every eligible persisted
    trade signal becomes AutoTrade-eligible through the same queue safety gates.
    M1, non-XAUUSD, WAIT/non-directional, closed/cancelled, and Book+OpenAI records
    are never forwarded. Existing queue de-duplication prevents duplicate orders.
    """
    if not MT5_AUTO_TRADING or not AUTO_ENTRY_ENABLED:
        return []
    rows = list(session.scalars(select(SignalHistory).where(
        SignalHistory.user_id == user_id,
        SignalHistory.created_at >= _HISTORY_AUTOTRADE_BRIDGE_STARTED_AT,
        SignalHistory.symbol == "XAU/USD",
        SignalHistory.direction.in_(["BUY", "SELL"]),
    ).order_by(SignalHistory.created_at.asc(), SignalHistory.id.asc()).limit(500)).all())
    forwarded = []
    for row in rows:
        status = _history_status(row)
        if status != "ACTIVE":
            continue
        if str(row.interval or "").strip().lower() in {"1m", "1min", "m1"}:
            continue
        source = str(row.source or HISTORY_DEFAULT_SOURCE)[:40]
        if _autotrade_source_excluded(source):
            continue
        try:
            payload = json.loads(row.payload or "{}")
        except Exception:
            payload = {}
        entry, sl, tps = _history_row_levels_for_autotrade(row, payload)
        if entry is None or sl is None or not tps:
            continue
        # Only History records explicitly marked AutoTrade-eligible can be forwarded.
        # RR >= 1.50 is a hard MT5 requirement; lower-RR signals remain History-only.
        gate_payload = payload.get("execution_gate") if isinstance(payload.get("execution_gate"), dict) else {}
        auto_flag = bool(gate_payload.get("auto_trade", payload.get("auto_trade_eligible", False)))
        try:
            rr_value = float(gate_payload.get("risk_reward") or payload.get("risk_reward") or row.risk_reward or 0)
        except Exception:
            rr_value = 0.0
        if not auto_flag or rr_value < 1.50:
            continue
        try:
            confidence = float(row.signal_score or payload.get("confidence_at_entry") or payload.get("confidence") or 0)
            existing_queue_ids = {str(q.get("id")) for q in MT5_ORDER_QUEUE}
            order = _queue_autotrade_order(
                symbol=row.symbol, source=source, interval=row.interval, direction=row.direction,
                entry=float(entry), sl=float(sl), tp=tps, volume=MT5_LOT_SIZE,
                confidence=confidence, candle_time=str(row.candle_time or row.created_at.isoformat()),
                risk_reward=rr_value,
            )
        except Exception as exc:
            print(f"[HISTORY AUTOTRADE BRIDGE] error signal_id={row.signal_uid} source={source}: {type(exc).__name__}: {exc}")
            continue
        if order is not None and str(order.get("id")) not in existing_queue_ids:
            forwarded.append({"signal_id": row.signal_uid, "source": source, "symbol": row.symbol,
                              "interval": row.interval, "direction": row.direction, "order_id": order.get("id")})
    return forwarded
MT5_ORDER_ATTEMPTS: dict[str, int] = {}
# MT5 V4 bridge client leases prevent multiple terminals sharing the same token from
# stealing each other's claimed orders. A dead client lease expires automatically.
MT5_BRIDGE_CLIENTS: dict[str, dict[str, Any]] = {}
MT5_CLAIM_LEASE_SECONDS = max(10, int(os.getenv("MT5_CLAIM_LEASE_SECONDS", "20")))
TRADINGVIEW_CACHE_TTL = float(os.getenv("TRADINGVIEW_CACHE_TTL", "2.0"))
TV_CANDLE_CACHE: dict[tuple[str,str], tuple[float, list[dict[str,Any]]]] = {}
TV_CANDLE_LOCKS: dict[tuple[str,str], asyncio.Lock] = {}
TV_CANDLE_LOCKS_GUARD = asyncio.Lock()
# Canonical snapshot cache shared by every strategy and endpoint. The cache key is
# strictly symbol + timeframe, so Technical Analysis, Algo/SMC, SMC, Fibonacci,
# Trend Channel, MSAI and MTF reuse identical OHLC data for the same request.
MARKET_SNAPSHOT_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
MARKET_SNAPSHOT_LOCKS: dict[tuple[str, str], asyncio.Lock] = {}
MARKET_SNAPSHOT_LOCKS_GUARD = asyncio.Lock()
MARKET_SNAPSHOT_TTL = max(0.5, float(os.getenv("MARKET_SNAPSHOT_TTL", "2.0")))
NODE_QUOTE_TIMEOUT = float(os.getenv("NODE_QUOTE_TIMEOUT", "2.5"))
MARKET_TIMEZONE = os.getenv("MARKET_TIMEZONE", "UTC").strip() or "UTC"
# SECRET_KEY is automatically generated when Railway does not provide one.
# A manually configured Railway SECRET_KEY always takes precedence.
# The generated key is unique for each running instance/process and is never sent to the frontend.
_configured_secret_key = os.getenv("SECRET_KEY", "").strip()
if _configured_secret_key:
    SECRET_KEY = _configured_secret_key
else:
    SECRET_KEY = secrets.token_urlsafe(64)
    print("[SignalX security] SECRET_KEY not set; generated a unique runtime key automatically.")
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
    # Server-side authorization role. New registrations are always ordinary users.
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    subscription: Mapped["Subscription | None"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class SessionToken(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_revoked: Mapped[bool] = mapped_column(default=False, index=True)


class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    plan: Mapped[str] = mapped_column(String(50), default="free")
    status: Mapped[str] = mapped_column(String(30), default="active")
    renews_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user: Mapped[User] = relationship(back_populates="subscription")


LEGACY_EXCLUDED_SIGNAL_SOURCES = {"Signal Lab", "AlgoTrade", "Book + OpenAI", "SNR", "Adaptive Institutional SNR V2", "Strong-zone SNR", "Signals", "Signal Engine"}
HISTORY_DEFAULT_SOURCE = "Unknown"

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
    source: Mapped[str] = mapped_column(String(40), default=HISTORY_DEFAULT_SOURCE, index=True)
    candle_time: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    signal_uid: Mapped[str] = mapped_column(String(40), unique=True, index=True, default=lambda: "SIG-" + secrets.token_hex(10).upper())
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    signal_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_strength: Mapped[str | None] = mapped_column(String(30), nullable=True)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_1: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_2: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_reward: Mapped[float | None] = mapped_column(Float, nullable=True)
    result: Mapped[str | None] = mapped_column(String(30), nullable=True)
    profit_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    r_multiple: Mapped[float | None] = mapped_column(Float, nullable=True)


Base.metadata.create_all(engine)

HISTORY_LOCAL_TZ = ZoneInfo("Asia/Tashkent")

def _purge_retired_signal_history(session: Session) -> int:
    """Delete retired standalone Signals/Signal Engine rows from the local history store.

    Controlled by PURGE_RETIRED_SIGNAL_HISTORY=true. Production history endpoints also
    exclude these sources even when purge is disabled, so old rows can never resurface.
    """
    if os.getenv("PURGE_RETIRED_SIGNAL_HISTORY", "false").lower() != "true":
        return 0
    result = session.execute(delete(SignalHistory).where(SignalHistory.source.in_({"Signals", "Signal Engine"})))
    session.commit()
    return int(result.rowcount or 0)

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
            if "role" not in columns:
                conn.exec_driver_sql("ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'user'")
            conn.exec_driver_sql("UPDATE users SET role = COALESCE(NULLIF(role, ''), 'user')")
            conn.exec_driver_sql("UPDATE users SET username = email WHERE username IS NULL OR username = ''")
            conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_username ON users (username)")
            sig_cols = {c["name"] for c in inspector.get_columns("signal_history")}
            if "source" not in sig_cols:
                conn.exec_driver_sql("ALTER TABLE signal_history ADD COLUMN source VARCHAR(40) DEFAULT 'Unknown'")
            if "candle_time" not in sig_cols:
                conn.exec_driver_sql("ALTER TABLE signal_history ADD COLUMN candle_time VARCHAR(40)")
            # Professional Signal History v2 fields. Existing rows remain intact.
            sig_cols = {c["name"] for c in inspect(engine).get_columns("signal_history")}
            extra_columns = {
                "signal_uid": "VARCHAR(40)", "status": "VARCHAR(20) DEFAULT 'ACTIVE'",
                "signal_score": "FLOAT", "signal_strength": "VARCHAR(30)",
                "entry_price": "FLOAT", "stop_loss": "FLOAT", "take_profit_1": "FLOAT",
                "take_profit_2": "FLOAT", "risk_reward": "FLOAT", "result": "VARCHAR(30)",
                "profit_loss": "FLOAT", "r_multiple": "FLOAT",
            }
            for col, ddl in extra_columns.items():
                if col not in sig_cols:
                    conn.exec_driver_sql(f"ALTER TABLE signal_history ADD COLUMN {col} {ddl}")
            conn.exec_driver_sql("UPDATE signal_history SET status = CASE WHEN status IS NULL OR status='' THEN CASE outcome WHEN 'OPEN' THEN 'ACTIVE' WHEN 'TP HIT' THEN 'TP2 HIT' WHEN 'SL HIT' THEN 'SL HIT' WHEN 'AMBIGUOUS' THEN 'CANCELLED' ELSE outcome END ELSE status END")
            conn.exec_driver_sql("UPDATE signal_history SET result = CASE WHEN result IS NULL AND outcome IN ('TP HIT','SL HIT') THEN outcome ELSE result END")
            # Backfill stable public IDs deterministically from DB IDs for legacy rows.
            try:
                conn.exec_driver_sql("UPDATE signal_history SET signal_uid = 'SIG-' || printf('%06d', id) WHERE signal_uid IS NULL OR signal_uid = ''")
            except Exception:
                conn.exec_driver_sql("UPDATE signal_history SET signal_uid = 'SIG-' || CAST(id AS VARCHAR) WHERE signal_uid IS NULL OR signal_uid = ''")
            sess_cols = {c["name"] for c in inspector.get_columns("sessions")}
            if "created_at" not in sess_cols:
                conn.exec_driver_sql("ALTER TABLE sessions ADD COLUMN created_at TIMESTAMP")
            if "last_seen_at" not in sess_cols:
                conn.exec_driver_sql("ALTER TABLE sessions ADD COLUMN last_seen_at TIMESTAMP")
            if "user_agent" not in sess_cols:
                conn.exec_driver_sql("ALTER TABLE sessions ADD COLUMN user_agent TEXT")
            if "device_model" not in sess_cols:
                conn.exec_driver_sql("ALTER TABLE sessions ADD COLUMN device_model VARCHAR(255)")
            if "is_revoked" not in sess_cols:
                conn.exec_driver_sql("ALTER TABLE sessions ADD COLUMN is_revoked BOOLEAN DEFAULT FALSE")
            conn.exec_driver_sql("UPDATE sessions SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP), last_seen_at = COALESCE(last_seen_at, CURRENT_TIMESTAMP), is_revoked = COALESCE(is_revoked, FALSE)")
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
        current.role = "admin"
        if not current.subscription:
            current.subscription = Subscription(plan="admin", status="active", renews_at=None)
        else:
            current.subscription.plan = "admin"
            current.subscription.status = "active"
        s.commit()


HISTORY_LIVE_VERSION = os.getenv("HISTORY_LIVE_VERSION", "live-only-2026-09-17-v3").strip() or "live-only-2026-09-17-v3"

def _prepare_live_history_once() -> None:
    """Start the new journal from live data only, once per persistent DB version.

    Existing history is intentionally removed because the journal schema/semantics have
    been changed and legacy rows were not reliable live-signal records. A DB marker makes
    this destructive cleanup one-time across Railway restarts.
    """
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE IF NOT EXISTS signal_history_runtime_state (key VARCHAR(100) PRIMARY KEY, value VARCHAR(255))")
        row = conn.exec_driver_sql("SELECT value FROM signal_history_runtime_state WHERE key='history_live_version'").fetchone()
        if row and str(row[0]) == HISTORY_LIVE_VERSION:
            return
        conn.exec_driver_sql("DELETE FROM signal_history")
        backend = engine.url.get_backend_name()
        if backend == "sqlite":
            conn.exec_driver_sql("INSERT OR REPLACE INTO signal_history_runtime_state (key,value) VALUES (?,?)", ("history_live_version", HISTORY_LIVE_VERSION))
        else:
            conn.exec_driver_sql("DELETE FROM signal_history_runtime_state WHERE key='history_live_version'")
            conn.exec_driver_sql("INSERT INTO signal_history_runtime_state (key,value) VALUES (%s,%s)", ("history_live_version", HISTORY_LIVE_VERSION))
    print(f"[HISTORY LIVE-ONLY] legacy history cleared; version={HISTORY_LIVE_VERSION}")

def _ensure_live_history_unique_index() -> None:
    """Enforce one History row per user/symbol/timeframe/module/live-candle."""
    # All legacy data has already been cleared by _prepare_live_history_once on the
    # first boot of this version, so the unique index can be created safely.
    with engine.begin() as conn:
        try:
            conn.exec_driver_sql("DROP INDEX IF EXISTS uq_signal_history_identity")
        except Exception:
            pass
        conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS uq_signal_history_live_identity ON signal_history (user_id, symbol, interval, source, candle_time)")

def initialize_database() -> None:
    ensure_schema()
    ensure_admin_user()
    _prepare_live_history_once()
    _ensure_live_history_unique_index()


# Production hardening: keep the algorithm server-side and expose only derived results.
# The public browser never receives Python source or provider secrets.
ENABLE_API_DOCS = os.getenv("ENABLE_API_DOCS", "false").strip().lower() == "true"
# Lightweight process-local abuse protection. It is intentionally conservative so
# normal chart polling/MT5 heartbeats are not blocked. Railway replicas each keep
# their own bucket; persistent authorization still happens server-side.
RATE_LIMIT_WINDOW_SECONDS = max(10, int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")))
RATE_LIMIT_MAX_REQUESTS = max(30, int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "180")))
MAX_REQUEST_BODY_BYTES = max(65536, int(os.getenv("MAX_REQUEST_BODY_BYTES", "1048576")))
RATE_LIMIT_EXEMPT_PATHS = {"/", "/health", "/favicon.ico"}
_RATE_BUCKETS: dict[str, tuple[float, int]] = {}
_LOGIN_FAILS: dict[str, tuple[float, int]] = {}
LOGIN_LOCK_SECONDS = max(30, int(os.getenv("LOGIN_LOCK_SECONDS", "300")))
LOGIN_MAX_FAILURES = max(3, int(os.getenv("LOGIN_MAX_FAILURES", "8")))
app = FastAPI(
    title=APP_TITLE,
    version="19.0.0",
    docs_url="/docs" if ENABLE_API_DOCS else None,
    redoc_url="/redoc" if ENABLE_API_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_API_DOCS else None,
)

# Default to same-site production origins. FRONTEND_ORIGINS can explicitly add approved
# development/staging origins without reopening CORS to the world.
origins_raw = os.getenv(
    "FRONTEND_ORIGINS",
    "https://signalx.asia,https://www.signalx.asia,https://xauusd-production-9fd9.up.railway.app"
)
origins = [x.strip() for x in origins_raw.split(",") if x.strip()] or ["https://signalx.asia"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)


@app.middleware("http")
async def abuse_protection_middleware(request: Request, call_next):
    path=request.url.path
    if path not in RATE_LIMIT_EXEMPT_PATHS:
        now=asyncio.get_running_loop().time()
        host=request.client.host if request.client else "unknown"
        key=f"{host}:{request.method}:{path.split('/')[1] if path.startswith('/') and len(path)>1 else path}"
        started,count=_RATE_BUCKETS.get(key,(now,0))
        if now-started >= RATE_LIMIT_WINDOW_SECONDS:
            started,count=now,0
        count += 1
        _RATE_BUCKETS[key]=(started,count)
        if count > RATE_LIMIT_MAX_REQUESTS:
            retry=max(1,int(RATE_LIMIT_WINDOW_SECONDS-(now-started)))
            return JSONResponse({"detail":"Too many requests. Try again shortly."}, status_code=429, headers={"Retry-After":str(retry),"Cache-Control":"no-store"})
    if request.headers.get("content-length"):
        try:
            if int(request.headers["content-length"]) > MAX_REQUEST_BODY_BYTES:
                return JSONResponse({"detail":"Request body too large."}, status_code=413)
        except ValueError:
            pass
    return await call_next(request)

@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
    response.headers.setdefault("X-Robots-Tag", "noindex, nofollow") if request.url.path.startswith("/api/") else None
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store, max-age=0")
        response.headers.setdefault("Pragma", "no-cache")
    if request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").lower() == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response



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
MSAI_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
MSAI_CACHE_TTL = float(os.getenv("MSAI_CACHE_TTL", "10"))
MSAI_AI_CACHE: dict[str, tuple[float, str | None, dict[str, Any]]] = {}
MSAI_AI_LOCKS: dict[str, asyncio.Lock] = {}
MSAI_AI_LOCKS_GUARD = asyncio.Lock()
SMC_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
SMC_CACHE_TTL = float(os.getenv("SMC_CACHE_TTL", "10"))
SMC_AI_CACHE: dict[str, tuple[float, str | None, dict[str, Any]]] = {}
SMC_AI_LOCKS: dict[str, asyncio.Lock] = {}
SMC_AI_LOCKS_GUARD = asyncio.Lock()
ALGO_SMC_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
ALGO_SMC_CACHE_TTL = float(os.getenv("ALGO_SMC_CACHE_TTL", "10"))
ADVANCED_CACHE_TTL = float(os.getenv("ADVANCED_CACHE_TTL", "5"))
MTF_CACHE_TTL = float(os.getenv("MTF_CACHE_TTL", "10"))
LIVE_PRICE_CACHE_TTL = float(os.getenv("LIVE_PRICE_CACHE_TTL", "1.5"))
AUTO_ENTRY_ENABLED = os.getenv("AUTO_ENTRY_ENABLED", "true").lower() == "true"
AUTO_ENTRY_THRESHOLD = 0.0  # disabled: AUTO TRADE forwards every eligible active-module signal
AUTO_ENTRY_DUPLICATE_MINUTES = int(os.getenv("AUTO_ENTRY_DUPLICATE_MINUTES", "5"))
AUTO_ENTRY_MIN_ZONE = 0.0  # disabled: zone-quality filter removed from AUTO TRADE
AUTO_ENTRY_MIN_AI_AGREEMENT = 0.0  # disabled: AI-agreement filter removed from AUTO TRADE
AUTO_ENTRY_REQUIRE_MTF = False  # disabled: MTF confirmation is not required for AUTO TRADE


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


def describe_device(user_agent: str | None) -> str:
    ua = (user_agent or "").strip()
    low = ua.lower()
    if not ua:
        return "Noma’lum qurilma"
    browser = "Brauzer"
    if "edg/" in low or "edge/" in low:
        browser = "Microsoft Edge"
    elif "opr/" in low or "opera" in low:
        browser = "Opera"
    elif "chrome/" in low and "edg/" not in low:
        browser = "Google Chrome"
    elif "firefox/" in low:
        browser = "Mozilla Firefox"
    elif "safari/" in low and "chrome/" not in low:
        browser = "Safari"
    os_name = "Unknown OS"
    if "windows" in low:
        os_name = "Windows PC"
    elif "android" in low:
        os_name = "Android qurilma"
    elif "iphone" in low or "ipad" in low or "ios" in low:
        os_name = "iPhone/iPad"
    elif "mac os x" in low or "macintosh" in low:
        os_name = "Mac"
    elif "linux" in low:
        os_name = "Linux PC"
    # Browsers generally do not expose the exact hardware model on desktop.
    # We therefore report the most reliable device family + browser.
    return f"{os_name} · {browser}"

def create_session(user_id: int, session: Session, user_agent: str | None = None) -> str:
    raw = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)
    item = SessionToken(
        user_id=user_id,
        token_hash=token_hash(raw),
        expires_at=now + timedelta(hours=SESSION_HOURS),
        created_at=now,
        last_seen_at=now,
        user_agent=(user_agent or "")[:4000] or None,
        device_model=describe_device(user_agent),
        is_revoked=False,
    )
    session.add(item)
    session.commit()
    return raw

def current_user(authorization: str | None, session: Session) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    raw = authorization.split(" ", 1)[1].strip()
    if secrets.compare_digest(raw, AUTOTRADE_INTERNAL_TOKEN):
        user = session.scalar(select(User).where(User.role == "admin").order_by(User.id.asc()))
        if user is None:
            user = session.scalar(select(User).order_by(User.id.asc()))
        if user is None:
            raise HTTPException(status_code=503, detail="No user exists for internal auto-trade worker")
        return user
    row = session.scalar(select(SessionToken).where(SessionToken.token_hash == token_hash(raw)))
    if not row or getattr(row, "is_revoked", False):
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    expiry = row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at.tzinfo is None else row.expires_at
    if expiry < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    row.last_seen_at = datetime.now(timezone.utc)
    session.commit()
    user = session.get(User, row.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def is_admin_user(user: User) -> bool:
    """Single source of truth for privileged dashboard access.

    Keep subscription-plan compatibility with older databases while making the
    explicit role authoritative for all newly registered accounts.
    """
    return str(getattr(user, "role", "user") or "user").lower() == "admin" or (
        user.subscription is not None and str(user.subscription.plan or "").lower() == "admin"
    )

def require_admin(authorization: str | None, session: Session) -> User:
    user = current_user(authorization, session)
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Bu bo‘lim faqat administrator uchun. Oddiy user AI tizimidan foydalana olmaydi.")
    return user


class AIChatBody(BaseModel):
    question: str = Field(min_length=2, max_length=1200)
    symbol: str = Field(default=DEFAULT_SYMBOL, min_length=3, max_length=32)
    interval: str = Field(default=DEFAULT_INTERVAL, min_length=2, max_length=16)

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
async def auth_login(body: AuthBody, request: Request, session: Session = Depends(db)) -> dict[str, Any]:
    """Stable username/password login endpoint used by the dashboard."""
    identity = body.username.strip()
    client_ip = request.client.host if request.client else "unknown"
    lock_key = f"{client_ip}|{identity.lower()}"
    now_mono = asyncio.get_running_loop().time()
    fail_started, fail_count = _LOGIN_FAILS.get(lock_key, (now_mono, 0))
    if now_mono - fail_started >= LOGIN_LOCK_SECONDS:
        fail_started, fail_count = now_mono, 0
    if fail_count >= LOGIN_MAX_FAILURES:
        retry = max(1, int(LOGIN_LOCK_SECONDS - (now_mono - fail_started)))
        raise HTTPException(status_code=429, detail=f"Too many login attempts. Try again in {retry}s.")
    user = session.scalar(select(User).where(User.username == identity))
    if user is None and valid_email(identity):
        user = session.scalar(select(User).where(User.email == identity.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        _LOGIN_FAILS[lock_key]=(fail_started, fail_count+1)
        raise HTTPException(status_code=401, detail="Login yoki parol noto‘g‘ri")
    _LOGIN_FAILS.pop(lock_key, None)
    raw = create_session(user.id, session, request.headers.get("user-agent"))
    plan = user.subscription.plan if user.subscription else "free"
    return {"token": raw, "user": {"id": user.id, "username": user.username, "email": user.email, "plan": plan, "role": getattr(user, "role", "user"), "is_admin": is_admin_user(user)}}


@app.post("/api/auth/register")
async def auth_register(body: RegisterBody, request: Request, session: Session = Depends(db)) -> dict[str, Any]:
    """Create a user without requiring SMTP; credentials are returned once so mobile users can enter them."""
    email = body.email.strip().lower()
    if not valid_email(email):
        raise HTTPException(status_code=422, detail="To‘g‘ri email manzilini kiriting")
    if session.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Bu email allaqachon ro‘yxatdan o‘tgan")
    login, password = generate_credentials()
    while session.scalar(select(User).where(User.username == login)):
        login, password = generate_credentials()
    user = User(email=email, username=login, role="user", password_hash=hash_password(password))
    session.add(user)
    session.flush()
    user.subscription = Subscription(plan="free", status="active")
    session.commit()
    raw = create_session(user.id, session, request.headers.get("user-agent"))
    email_ok, email_message = send_credentials_email(email, login, password)
    return {
        "token": raw,
        "user": {"id": user.id, "username": login, "email": email, "plan": "free", "role": "user", "is_admin": False},
        "credentials": {"login": login, "password": password},
        "email_message": email_message if email_ok else "Email yuborilmadi, login/parol shu yerda ko‘rsatildi."
    }


@app.post("/api/auth/logout")
async def auth_logout(authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization.split(" ", 1)[1].strip()
        row = session.scalar(select(SessionToken).where(SessionToken.token_hash == token_hash(raw)))
        if row:
            row.is_revoked = True
            row.last_seen_at = datetime.now(timezone.utc)
            session.commit()
    return {"ok": True}


@app.get("/api/auth/me")
async def auth_me(authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    user = current_user(authorization, session)
    plan = user.subscription.plan if user.subscription else "free"
    return {"user": {"id": user.id, "username": user.username, "email": user.email, "plan": plan, "role": getattr(user, "role", "user"), "is_admin": is_admin_user(user)}}

@app.get("/api/auth/sessions")
async def auth_sessions(authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    # Privacy rule: ordinary users can see only their own sessions; admins can
    # see all users' active/non-revoked sessions. This is enforced server-side.
    user = current_user(authorization, session)
    now = datetime.now(timezone.utc)
    if is_admin_user(user):
        # A multi-entity SELECT must use execute(), not scalars(); scalars()
        # would discard the User entity and cause tuple-unpacking below to
        # raise HTTP 500 on the Active Sessions page.
        rows = list(session.execute(
            select(SessionToken, User)
            .join(User, SessionToken.user_id == User.id)
            .order_by(SessionToken.last_seen_at.desc())
        ).all())
    else:
        rows = [(row, user) for row in session.scalars(
            select(SessionToken)
            .where(SessionToken.user_id == user.id)
            .order_by(SessionToken.last_seen_at.desc())
        )]

    items = []
    raw = authorization.split(" ", 1)[1].strip() if authorization and authorization.lower().startswith("bearer ") else ""
    current_hash = token_hash(raw) if raw else ""
    for row, owner in rows:
        exp = row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at and row.expires_at.tzinfo is None else row.expires_at
        seen = row.last_seen_at.replace(tzinfo=timezone.utc) if row.last_seen_at and row.last_seen_at.tzinfo is None else row.last_seen_at
        active = bool(seen and (now - seen).total_seconds() <= 30 * 60 and not row.is_revoked and exp and exp >= now)
        if not active and row.is_revoked:
            continue
        item = {
            "id": row.id,
            "user_id": owner.id,
            "username": owner.username or "—",
            "email": owner.email or "",
            "device_model": row.device_model or "Noma’lum qurilma",
            "user_agent": row.user_agent or "",
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "active": active,
            "current": row.token_hash == current_hash,
        }
        # Do not leak another user's identity to ordinary users.
        if not is_admin_user(user):
            item.pop("user_id", None)
            item.pop("username", None)
            item.pop("email", None)
        items.append(item)
    return {"sessions": items, "scope": "all" if is_admin_user(user) else "self", "is_admin": is_admin_user(user)}

@app.post("/api/auth/sessions/{session_id}/revoke")
async def revoke_one_session(session_id: int, authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    """Revoke one session. Admins may revoke any user's session; normal users may revoke only their own."""
    user = current_user(authorization, session)
    row = session.get(SessionToken, session_id)
    if not row:
        raise HTTPException(status_code=404, detail="Seans topilmadi")
    if not is_admin_user(user) and row.user_id != user.id:
        raise HTTPException(status_code=403, detail="Faqat o'zingizga tegishli seansni yopishingiz mumkin")
    if row.is_revoked:
        return {"ok": True, "revoked": 0, "session_id": session_id, "already_revoked": True}
    row.is_revoked = True
    row.last_seen_at = datetime.now(timezone.utc)
    session.commit()
    return {"ok": True, "revoked": 1, "session_id": session_id, "current": False}


@app.post("/api/auth/sessions/revoke-all")
async def revoke_all_sessions(authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    """Revoke all sessions belonging to the current user, including the current one."""
    user = current_user(authorization, session)
    rows = list(session.scalars(select(SessionToken).where(SessionToken.user_id == user.id, SessionToken.is_revoked == False)))
    count = 0
    for row in rows:
        row.is_revoked = True
        row.last_seen_at = datetime.now(timezone.utc)
        count += 1
    session.commit()
    return {"ok": True, "revoked": count, "logged_out": True}


@app.post("/api/auth/sessions/revoke-others")
async def revoke_other_sessions(authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    user = current_user(authorization, session)
    raw = authorization.split(" ", 1)[1].strip() if authorization and authorization.lower().startswith("bearer ") else ""
    current_hash = token_hash(raw) if raw else ""
    rows = list(session.scalars(select(SessionToken).where(SessionToken.user_id == user.id)))
    count = 0
    for row in rows:
        if row.token_hash != current_hash and not row.is_revoked:
            row.is_revoked = True
            count += 1
    session.commit()
    return {"ok": True, "revoked": count}


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

def _normalize_history_candle_time(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return str(int(float(raw)))
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return str(int(dt.timestamp()))
    except Exception:
        return raw


def _normalize_history_source(value: str | None) -> str:
    raw = str(value or HISTORY_DEFAULT_SOURCE).strip()
    aliases = {
        "signals":"Signals", "signal engine":"Signal Engine", "technical analysis":"Technical Analysis",
        "ai smart analysis":"AI Smart Analysis", "ai fallback network":"AI Fallback Network",
        "auto trend line":"Auto Trend Line", "trend line":"Trend Line", "ict signals":"ICT Signals",
        "ict":"ICT Signals", "multi timeframe":"Multi-Timeframe", "multi-timeframe":"Multi-Timeframe", "classic trade":"Classic Trade",
        "consensus":"Consensus", "smc":"SMC", "algo/smc":"Algo/SMC", "msai strategy":"MSAI/SNR", "msai/snr":"MSAI/SNR",
        "trend channel engine":"Trend Channel Engine", "trend channel":"Trend Channel Engine",
        "fibonacci":"Fibonacci", "new strategy":"Yangi Strategiya", "yangi strategiya":"Yangi Strategiya",
        "economic calendar":"Economic Calendar", "market sessions":"Market Sessions", "patterns":"Patterns", "pattern":"Patterns"
    }
    return aliases.get(raw.lower(), raw)[:40]

def history_pip_size(symbol: str) -> float:
    """Return the user-facing pip size for history distance display.
    XAUUSD uses 0.01 price units per pip; major FX pairs use 0.0001.
    """
    key = clean_symbol(symbol).replace('/', '')
    if key.startswith('XAU'):
        return 0.01
    if key.endswith('JPY'):
        return 0.01
    return 0.0001

def history_level_pips(symbol: str, entry: float | None, tp: Any, sl: float | None) -> tuple[float | None, float | None, float | None]:
    """Calculate per-signal TP/SL pip distances, isolated by symbol.
    tp_pips is the distance to the furthest TP; tp_pips_total is the sum of
    distances from Entry to every TP target; sl_pips is the Entry→SL distance.
    """
    try:
        e = float(entry) if entry is not None else None
    except (TypeError, ValueError):
        e = None
    pip = history_pip_size(symbol)
    if e is None or pip <= 0:
        return None, None, None
    raw = tp if isinstance(tp, list) else ([] if tp in (None, '') else [tp])
    tps = []
    for value in raw:
        try:
            tps.append(float(value))
        except (TypeError, ValueError):
            continue
    tp_distances = [abs(v - e) / pip for v in tps]
    tp_farthest = max(tp_distances) if tp_distances else None
    tp_total = sum(tp_distances) if tp_distances else None
    try:
        sl_pips = abs(float(sl) - e) / pip if sl is not None else None
    except (TypeError, ValueError):
        sl_pips = None
    return (round(tp_farthest, 2) if tp_farthest is not None else None,
            round(tp_total, 2) if tp_total is not None else None,
            round(sl_pips, 2) if sl_pips is not None else None)

def realmarket_symbol(symbol: str) -> str:
    return clean_symbol(symbol).replace("/", "")

REALMARKET_TIMEFRAMES = {"1min":"M1","5min":"M5","15min":"M15","1h":"H1","4h":"H4","1day":"D1"}

def realmarket_timeframe(interval: str) -> str:
    interval = validate_interval(interval)
    if interval not in REALMARKET_TIMEFRAMES:
        raise MarketDataError(f"RealMarketAPI does not publish {interval} in its documented timeframe set; use Twelve Data for this timeframe.")
    return REALMARKET_TIMEFRAMES[interval]

def _market_provider_enabled(provider: str) -> bool:
    provider = str(provider or "").lower().strip()
    if provider == "tradingview":
        return True
    if provider == "realmarketapi":
        return bool(REALMARKET_API_KEY)
    if provider == "twelvedata":
        return bool(TWELVE_DATA_API_KEY)
    if provider == "yahoo":
        return True
    return False


def _market_provider_order() -> list[str]:
    preferred = MARKET_PROVIDER.strip().lower() or "auto"
    order = []
    if preferred in {"realmarket", "realmarketapi"}:
        order.append("realmarketapi")
    elif preferred == "twelvedata":
        order.append("twelvedata")
    elif preferred == "yahoo":
        order.append("yahoo")
    elif preferred == "tradingview":
        order.append("tradingview")
    for provider in MARKET_FALLBACK_ORDER:
        if provider not in order:
            order.append(provider)
    return [p for p in order if _market_provider_enabled(p)]


def _mark_market_provider_success(provider: str, *, symbol: str, interval: str, candles: list[dict[str, Any]]) -> None:
    MARKET_PROVIDER_COOLDOWN_UNTIL.pop(provider, None)
    MARKET_PROVIDER_STATUS[provider] = {
        "status": "ONLINE",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "interval": interval,
        "bars": len(candles),
        "last_error": "",
    }


def _mark_market_provider_failure(provider: str, exc: Exception) -> str:
    now_mono = asyncio.get_running_loop().time()
    cooldown_until = now_mono + MARKET_PROVIDER_COOLDOWN_SECONDS
    MARKET_PROVIDER_COOLDOWN_UNTIL[provider] = cooldown_until
    message = f"{type(exc).__name__}: {exc}"[:400]
    MARKET_PROVIDER_STATUS[provider] = {
        "status": "OFFLINE",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "error": message,
        "cooldown_until": cooldown_until,
    }
    return message


def _market_provider_name(provider: str) -> str:
    return {
        "tradingview": "TradingView",
        "realmarketapi": "RealMarketAPI",
        "twelvedata": "Twelve Data",
        "yahoo": "Yahoo Finance",
    }.get(provider, provider)


async def _fetch_market_candles_provider(provider: str, symbol: str, interval: str, limit: int) -> list[dict[str, Any]]:
    if provider == "tradingview":
        return await fetch_tradingview_candles(symbol, interval, limit, allow_stale=False)
    if provider == "realmarketapi":
        return await fetch_realmarket_candles(symbol, interval, limit)
    if provider == "twelvedata":
        return await fetch_twelvedata_candles(symbol, interval, limit)
    if provider == "yahoo":
        return await fetch_yahoo_candles(symbol, interval, limit)
    raise MarketDataError(f"Unknown market provider: {provider}")


def _normalize_market_candles(candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for c in candles or []:
        try:
            item = {
                "time": int(float(c["time"])),
                "open": float(c["open"]),
                "high": float(c["high"]),
                "low": float(c["low"]),
                "close": float(c["close"]),
            }
        except (KeyError, TypeError, ValueError):
            continue
        if not all(math.isfinite(item[k]) for k in ("open", "high", "low", "close")):
            continue
        if item["high"] < max(item["open"], item["close"]) or item["low"] > min(item["open"], item["close"]):
            continue
        normalized.append(item)
    dedup = {c["time"]: c for c in normalized}
    return [dedup[k] for k in sorted(dedup)]


async def get_market_snapshot(symbol: str, interval: str, limit: int = 220) -> dict[str, Any]:
    """Canonical market snapshot with provider failover.

    The selected provider is recorded with the snapshot and the same snapshot is
    reused by every module for this symbol/timeframe until its short TTL expires.
    A provider failure is isolated with a cooldown, so the router immediately moves
    to the next configured provider instead of returning an empty series.
    """
    key = clean_symbol(symbol)
    interval = validate_interval(interval)
    limit = max(2, min(int(limit), 500))
    cache_key = (key, interval)
    now_mono = asyncio.get_running_loop().time()
    cached = MARKET_SNAPSHOT_CACHE.get(cache_key)
    if cached and now_mono - cached[0] < MARKET_SNAPSHOT_TTL:
        return cached[1]

    async with MARKET_SNAPSHOT_LOCKS_GUARD:
        lock = MARKET_SNAPSHOT_LOCKS.setdefault(cache_key, asyncio.Lock())
    async with lock:
        now_mono = asyncio.get_running_loop().time()
        cached = MARKET_SNAPSHOT_CACHE.get(cache_key)
        if cached and now_mono - cached[0] < MARKET_SNAPSHOT_TTL:
            return cached[1]

        errors: list[dict[str, str]] = []
        providers = _market_provider_order()
        if not providers:
            raise MarketDataError("No market-data providers are configured")

        for provider in providers:
            cooldown = MARKET_PROVIDER_COOLDOWN_UNTIL.get(provider, 0.0)
            if cooldown > now_mono:
                errors.append({"provider": provider, "error": "provider cooldown active"})
                continue
            try:
                candles = _normalize_market_candles(await _fetch_market_candles_provider(provider, key, interval, limit))
                minimum = 35 if interval in {"1min", "5min", "15min", "30min"} else 40
                if len(candles) < min(minimum, limit):
                    raise MarketDataError(f"{_market_provider_name(provider)} returned only {len(candles)} usable candles")
                candles = candles[-limit:]
                current_price = float(candles[-1]["close"])
                snapshot = {
                    "symbol": key,
                    "interval": interval,
                    "provider": provider,
                    "provider_name": _market_provider_name(provider),
                    "mode": "live",
                    "current_price": current_price,
                    "candle": candles[-1],
                    "candles": candles,
                    "warning": (
                        f"Primary market provider failed; automatically switched to {_market_provider_name(provider)}."
                        if errors else None
                    ),
                    "provider_errors": errors,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }
                _mark_market_provider_success(provider, symbol=key, interval=interval, candles=candles)
                MARKET_SNAPSHOT_CACHE[cache_key] = (asyncio.get_running_loop().time(), snapshot)
                return snapshot
            except Exception as exc:
                errors.append({"provider": provider, "error": _mark_market_provider_failure(provider, exc)})

        detail = " | ".join(f"{e['provider']}: {e['error']}" for e in errors)
        raise MarketDataError(f"All market-data providers failed for {key} {interval}. {detail}")


def live_provider() -> str | None:
    """Return the preferred configured live provider (router still fails over)."""
    order = _market_provider_order()
    return order[0] if order else None


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
        entry = float(current["close"])
        sl = max(float(current["high"]), float(pivot)) * (1 + SL_BUFFER_PCT)
        # Never place a SELL target above/at entry. If S1 is already behind price,
        # advance to the next valid support; if no valid support remains, WAIT.
        sell_targets = [float(levels["s1"]), float(levels["s2"]), float(levels["s3"])]
        sell_targets = [x for x in sell_targets if x < entry]
        if len(sell_targets) >= 2:
            result.update(signal="SELL", setup="PIVOT_RETEST" if bearish_retest else "S1_BREAKOUT", entry=round(entry, 2), stop_loss=round(sl, 2), take_profit=[round(sell_targets[0], 2), round(sell_targets[1], 2)], reason="Bearish Pivot filter confirmed with rejection/breakdown.")
        else:
            result.update(setup="TARGET_REACHED", reason="Bearish setup has no valid support target below entry; fresh SELL entry blocked.")
    elif bias == "BULLISH" and (bullish_retest or bullish_breakout):
        entry = float(current["close"])
        sl = min(float(current["low"]), float(pivot)) * (1 - SL_BUFFER_PCT)
        # Never place a BUY target below/at entry. If R1 is already behind price,
        # advance to the next valid resistance; if no valid resistance remains, WAIT.
        buy_targets = [float(levels["r1"]), float(levels["r2"]), float(levels["r3"])]
        buy_targets = [x for x in buy_targets if x > entry]
        if len(buy_targets) >= 2:
            result.update(signal="BUY", setup="PIVOT_RETEST" if bullish_retest else "R1_BREAKOUT", entry=round(entry, 2), stop_loss=round(sl, 2), take_profit=[round(buy_targets[0], 2), round(buy_targets[1], 2)], reason="Bullish Pivot filter confirmed with rejection/breakout.")
        else:
            result.update(setup="TARGET_REACHED", reason="Bullish setup has no valid resistance target above entry; fresh BUY entry blocked.")
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
    snapshot = await get_market_snapshot(symbol, interval, min(CANDLE_LIMIT, 500))
    return snapshot["candles"], "market-router", snapshot.get("warning")


def _tv_session(prefix: str) -> str:
    return prefix + "_" + "".join(random.choice(string.ascii_lowercase) for _ in range(12))

def _tv_frame(method: str, params: list[Any]) -> str:
    payload=json.dumps({"m":method,"p":params},separators=(",",":"))
    return f"~m~{len(payload.encode('utf-8'))}~m~{payload}"

def tv_symbol_for(symbol: str) -> str:
    """Return the TradingView symbol matching the requested instrument page."""
    key = clean_symbol(symbol)
    return os.getenv("TRADINGVIEW_SYMBOL", "OANDA:XAUUSD").strip() or "OANDA:XAUUSD"

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
            tv_symbol = tv_symbol_for(symbol)
            await send("quote_add_symbols",[qs,tv_symbol])
            resolve=json.dumps({"symbol":tv_symbol,"adjustment":"splits","session":"regular"},separators=(",",":"))
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


async def fetch_tradingview_candles(symbol: str, interval: str, limit: int = TRADINGVIEW_BARS, allow_stale: bool = True) -> list[dict[str, Any]]:
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
            if allow_stale:
                stale = TV_CANDLE_CACHE.get(key)
                if stale and stale[1]:
                    return stale[1][-limit:]
            if last_exc:
                raise last_exc
            raise MarketDataError("TradingView returned no fresh OHLC bars")
        bars = sorted({int(b["time"]): b for b in bars}.values(), key=lambda x: x["time"])
        TV_CANDLE_CACHE[key] = (asyncio.get_running_loop().time(), bars[-TRADINGVIEW_BARS:])
        return TV_CANDLE_CACHE[key][1][-limit:]


async def fetch_tradingview_price(symbol: str) -> float:
    """Return the latest TradingView quote for the requested instrument."""
    tv_symbol = tv_symbol_for(symbol)
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
    raise MarketDataError(f"TradingView {tv_symbol} quote unavailable. " + " | ".join(errors))


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
    """Return price from the canonical market snapshot used by analysis."""
    snapshot = await get_market_snapshot(symbol, interval, 220)
    return float(snapshot["current_price"]), snapshot["provider_name"]


def merge_live_price_into_candles(candles: list[dict[str, Any]], interval: str, price: float) -> list[dict[str, Any]]:
    """Update the currently-forming candle with a provider-matched quote."""
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
    return out[-max(2, min(len(out), 500)): ]


async def get_candles(symbol: str, interval: str, limit: int) -> tuple[list[dict[str, Any]], str, str | None]:
    """Canonical market data entry point shared by every strategy.

    The router uses the same symbol/timeframe snapshot across all modules and
    automatically fails over TradingView -> configured paid providers -> Yahoo.
    """
    snapshot = await get_market_snapshot(symbol, interval, max(31, min(limit, 500)))
    provider = snapshot["provider_name"]
    warning = snapshot.get("warning")
    if snapshot.get("provider_errors") and not warning:
        warning = "Market provider fallback active."
    return snapshot["candles"][-limit:], "market-router", warning


async def get_pivot_reference(symbol: str) -> tuple[dict[str, float], str | None]:
    snapshot = await get_market_snapshot(symbol, "1day", 5)
    data = snapshot["candles"]
    if not data:
        raise MarketDataError("Daily market candles unavailable for pivot")
    base = data[-2] if len(data) >= 2 else data[-1]
    return {"high": float(base["high"]), "low": float(base["low"]), "close": float(base["close"])}, snapshot.get("warning")

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



def _adaptive_regime(candles: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic market-regime layer used by the upgraded strategy engines.
    It is deliberately based only on the supplied timeframe candles."""
    closes=[float(c["close"]) for c in candles]
    if len(closes)<40:
        return {"regime":"UNKNOWN","trend_strength":0,"volatility":"UNKNOWN","momentum":"NEUTRAL"}
    av=max(atr(candles), 1e-9)
    fast=_linear_slope(closes[-30:]); slow=_linear_slope(closes[-100:])
    price=closes[-1]
    slope_ratio=abs(fast)/max(av/10.0,1e-9)
    recent_ranges=[max(float(c["high"])-float(c["low"]),0.0) for c in candles[-20:]]
    base_ranges=[max(float(c["high"])-float(c["low"]),0.0) for c in candles[-100:-20]] or recent_ranges
    vr=sum(recent_ranges)/max(len(recent_ranges),1) / max(sum(base_ranges)/max(len(base_ranges),1),1e-9)
    trend_strength=int(max(0,min(100,round(min(1.0,slope_ratio/3.0)*100))))
    if vr>=1.55: vol="HIGH"
    elif vr<=0.72: vol="LOW"
    else: vol="NORMAL"
    if trend_strength>=62 and fast*slow>0: regime="TRENDING_UP" if fast>0 else "TRENDING_DOWN"
    elif vr>=1.35 and trend_strength<55: regime="BREAKOUT_VOLATILE"
    else: regime="RANGE"
    mom="BULLISH" if fast>0 and price>=_ema(closes[-80:],20) else "BEARISH" if fast<0 and price<=_ema(closes[-80:],20) else "NEUTRAL"
    return {"regime":regime,"trend_strength":trend_strength,"volatility":vol,"volatility_ratio":round(vr,2),"momentum":mom}

def _strategy_profile(interval: str) -> dict[str, Any]:
    # Dedicated Strategic Pro profile for each analysis timeframe.
    # Higher TFs use wider structural context; lower TFs use tighter microstructure.
    profiles = {
        "1min":{"strategy":"Microstructure Liquidity Pro","min_confirmations":5,"min_quality":78,"min_score":90,"max_risk_atr":1.20},
        "5min":{"strategy":"ICT Liquidity + Displacement Pro","min_confirmations":6,"min_quality":78,"min_score":85,"max_risk_atr":2.20},
        "15min":{"strategy":"Intraday Structure + OB/FVG Pro","min_confirmations":5,"min_quality":76,"min_score":82,"max_risk_atr":2.50},
        "30min":{"strategy":"Institutional Structure + Liquidity Pro","min_confirmations":5,"min_quality":74,"min_score":80,"max_risk_atr":2.80},
        "1h":{"strategy":"HTF Trend + Structure Pro","min_confirmations":4,"min_quality":72,"min_score":78,"max_risk_atr":3.00},
        "4h":{"strategy":"Macro ICT + Liquidity Pro","min_confirmations":4,"min_quality":70,"min_score":75,"max_risk_atr":3.50},
        "1day":{"strategy":"Daily Macro Structure Pro","min_confirmations":3,"min_quality":68,"min_score":72,"max_risk_atr":4.00},
    }
    return profiles.get(interval,{"strategy":"Adaptive Strategic Pro","min_confirmations":4,"min_quality":70,"min_score":80,"max_risk_atr":3.0})

def _strategy_chain(interval: str) -> list[str]:
    return [
        "Live OHLC", "Market Regime", "Technical", "Pattern Detector", "Breakout", "Trend Line",
        "Fibonacci", "Liquidity", "Order Block", "FVG", "BOS/CHOCH",
        "ICT", "MTF Context", "AI Validation", "Final Signal", "MT5 AutoTrade"
    ]

def _enhance_strategy_result(item: dict[str, Any], candles: list[dict[str, Any]], interval: str) -> dict[str, Any]:
    """Common quality/anti-noise layer. It does not expose formulas to the client."""
    out=dict(item)
    regime=_adaptive_regime(candles); profile=_strategy_profile(interval)
    direction=str(out.get("signal") or out.get("direction") or "WAIT").upper()
    components=out.get("components") or {}
    confirms=int(out.get("confirmations") or 0)
    quality=int(out.get("confidence") or out.get("trend_power") or 0)
    # Penalize regime conflict instead of forcing a trade.
    conflict=False
    if direction=="BUY" and regime["regime"]=="TRENDING_DOWN": conflict=True
    if direction=="SELL" and regime["regime"]=="TRENDING_UP": conflict=True
    if conflict:
        quality=max(0,quality-18)
        out["pre_strategy_signal"]=direction
        direction="WAIT"
    # High volatility on 1M/5M requires a stronger candle/structure confirmation.
    if direction in {"BUY","SELL"} and interval in {"1min","5min"} and regime["volatility"]=="HIGH" and confirms < profile["min_confirmations"]+1:
        out["pre_strategy_signal"]=direction; direction="WAIT"
    if direction in {"BUY","SELL"} and confirms < profile["min_confirmations"]:
        out["pre_strategy_signal"]=direction; direction="WAIT"
    if direction in {"BUY","SELL"} and quality < profile["min_quality"]:
        out["pre_strategy_signal"]=direction; direction="WAIT"
    out["signal"]=direction
    out["strategy_engine"]="SignalX Strategy Engine V2"
    out["strategy_version"]="V2"
    out["market_regime"]=regime
    out["strategy_profile"]=profile
    out["strategy_chain"]=_strategy_chain(interval)
    out["chain_timeframe"]=interval
    out["strategy_quality"]=quality
    out["strategy_conflict"]=conflict
    out["decision_state"]="CONFIRMED" if direction in {"BUY","SELL"} else "WAIT"
    return out

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
    regime=_adaptive_regime(candles_data)
    closes=[float(c["close"]) for c in candles_data]
    ema20=_ema(closes[-80:],20); ema50=_ema(closes[-120:],50)
    macd=_ema(closes[-120:],12)-_ema(closes[-120:],26)
    technical_bias="BULLISH" if ema20>ema50 and macd>=0 else "BEARISH" if ema20<ema50 and macd<=0 else "MIXED"
    return {
        "rsi": round(r, 2), "rsi_state": rsi_state, "atr": round(a, 4),
        "ema20":round(ema20,4), "ema50":round(ema50,4), "macd":round(macd,6),
        "pivot": levels["pivot"], "support": [levels["s1"], levels["s2"], levels["s3"]],
        "resistance": [levels["r1"], levels["r2"], levels["r3"]],
        "trend": levels["bias"], "technical_bias":technical_bias, "signal": setup["signal"],
        "market_regime":regime,
        "summary": f"RSI {r:.1f} ({rsi_state}); EMA20/50 {technical_bias}; Pivot {levels['pivot']:.2f}; trend {levels['bias']}; setup {setup['setup']}."
    }




def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    k = 2.0 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def _bollinger_snapshot(closes: list[float], period: int = 20, mult: float = 2.0) -> dict[str, Any]:
    if len(closes) < period:
        return {"available": False}
    data = closes[-period:]
    mid = sum(data) / period
    variance = sum((x - mid) ** 2 for x in data) / period
    std = variance ** 0.5
    upper = mid + mult * std
    lower = mid - mult * std
    width = upper - lower
    return {
        "available": True,
        "upper": upper,
        "middle": mid,
        "lower": lower,
        "width": width,
        "position": (closes[-1] - lower) / max(width, 1e-9),
    }


def _macd_snapshot(closes: list[float]) -> dict[str, float | str]:
    if len(closes) < 35:
        return {"line": 0.0, "signal": 0.0, "histogram": 0.0, "state": "NEUTRAL"}
    macd_series: list[float] = []
    window = closes[-100:]
    for i in range(26, len(window) + 1):
        chunk = window[:i]
        macd_series.append(_ema(chunk, 12) - _ema(chunk, 26))
    line = macd_series[-1]
    signal = _ema(macd_series[-9:], 9) if len(macd_series) >= 9 else line
    hist = line - signal
    if line > signal and line > 0:
        state = "STRONG_BULLISH"
    elif line > signal:
        state = "BULLISH"
    elif line < signal and line < 0:
        state = "STRONG_BEARISH"
    elif line < signal:
        state = "BEARISH"
    else:
        state = "NEUTRAL"
    return {"line": line, "signal": signal, "histogram": hist, "state": state}


def _classic_book_patterns(candles: list[dict[str, Any]], atr_value: float) -> dict[str, Any]:
    """Deterministic patterns/confluence from the supplied trading books.

    Includes the classic double/triple reversal structures, rejection candles,
    breakout/retest confirmation, and Fibonacci/volatility context. It never
    creates a signal from one pattern alone.
    """
    n = len(candles)
    price = float(candles[-1]["close"])
    highs, lows = _swing_points(candles, 2, 2)
    tol = max(float(atr_value) * 0.45, abs(price) * 0.0012)

    def _between_lo(a: int, b: int) -> float:
        lo, hi = sorted((a, b))
        if hi - lo <= 1:
            return min(float(candles[lo]["low"]), float(candles[hi]["low"]))
        return min(float(candles[i]["low"]) for i in range(lo, hi + 1))

    def _between_hi(a: int, b: int) -> float:
        lo, hi = sorted((a, b))
        if hi - lo <= 1:
            return max(float(candles[lo]["high"]), float(candles[hi]["high"]))
        return max(float(candles[i]["high"]) for i in range(lo, hi + 1))

    chart_pattern = "NONE"
    pattern_direction = "NEUTRAL"
    pattern_confirmed = False
    neckline = None

    # Double/triple top and bottom patterns are only promoted when their
    # confirmation level has actually broken on the last completed candle.
    recent_highs = highs[-4:]
    recent_lows = lows[-4:]
    if len(recent_highs) >= 2:
        p1, p2 = recent_highs[-2], recent_highs[-1]
        if abs(p1[1] - p2[1]) <= tol:
            neckline = _between_lo(p1[0], p2[0])
            if len(recent_highs) >= 3:
                p0 = recent_highs[-3]
                if abs(p0[1] - p1[1]) <= tol * 1.15 and price < neckline:
                    chart_pattern = "TRIPLE TOP CONFIRMED"
                    pattern_direction = "BEARISH"
                    pattern_confirmed = True
            if not pattern_confirmed and price < neckline:
                chart_pattern = "DOUBLE TOP CONFIRMED"
                pattern_direction = "BEARISH"
                pattern_confirmed = True

    if chart_pattern == "NONE" and len(recent_lows) >= 2:
        p1, p2 = recent_lows[-2], recent_lows[-1]
        if abs(p1[1] - p2[1]) <= tol:
            neckline = _between_hi(p1[0], p2[0])
            if len(recent_lows) >= 3:
                p0 = recent_lows[-3]
                if abs(p0[1] - p1[1]) <= tol * 1.15 and price > neckline:
                    chart_pattern = "TRIPLE BOTTOM CONFIRMED"
                    pattern_direction = "BULLISH"
                    pattern_confirmed = True
            if not pattern_confirmed and price > neckline:
                chart_pattern = "DOUBLE BOTTOM CONFIRMED"
                pattern_direction = "BULLISH"
                pattern_confirmed = True

    cur = candles[-2] if n >= 2 else candles[-1]
    prev = candles[-3] if n >= 3 else cur
    o, h, l, c = map(float, (cur["open"], cur["high"], cur["low"], cur["close"]))
    body = abs(c - o); rng = max(h - l, 1e-9)
    upper_wick = h - max(o, c); lower_wick = min(o, c) - l
    hammer = lower_wick >= body * 2.0 and upper_wick <= max(body * 0.75, rng * 0.20) and c >= l + rng * 0.55
    shooting_star = upper_wick >= body * 2.0 and lower_wick <= max(body * 0.75, rng * 0.20) and c <= l + rng * 0.45
    inside_bar = float(cur["high"]) <= float(prev["high"]) and float(cur["low"]) >= float(prev["low"])
    candle_signal = "HAMMER" if hammer else "SHOOTING STAR" if shooting_star else "INSIDE BAR" if inside_bar else "NONE"

    # Breakout + retest: a close must cross a recent swing boundary, and the
    # current completed candle must hold that boundary rather than merely wick it.
    breakout_retest = "NONE"
    breakout_level = None
    if highs:
        rh = highs[-1][1]
        if float(candles[-3]["close"]) <= rh and c > rh and float(cur["low"]) >= rh - max(atr_value * 0.35, 1e-9):
            breakout_retest = "BULLISH_BREAKOUT_RETEST"
            breakout_level = rh
    if breakout_retest == "NONE" and lows:
        rl = lows[-1][1]
        if float(candles[-3]["close"]) >= rl and c < rl and float(cur["high"]) <= rl + max(atr_value * 0.35, 1e-9):
            breakout_retest = "BEARISH_BREAKOUT_RETEST"
            breakout_level = rl

    fib = _fibonacci_analysis(candles)
    fib_confluence = False
    fib_level = None
    if fib.get("available") and fib.get("direction") in {"BULLISH", "BEARISH"}:
        atr_pad = max(atr_value * 0.35, abs(price) * 0.0007)
        levels = fib.get("levels") or {}
        key = ["0.5", "0.618", "0.786"]
        nearest = min(key, key=lambda k: abs(price - float(levels[k]))) if all(k in levels for k in key) else None
        if nearest and abs(price - float(levels[nearest])) <= atr_pad:
            fib_confluence = True
            fib_level = nearest

    bb = _bollinger_snapshot([float(x["close"]) for x in candles])
    bb_state = "NORMAL"
    if bb.get("available"):
        width = float(bb["width"])
        prior = _bollinger_snapshot([float(x["close"]) for x in candles[:-1]])
        if prior.get("available") and width > float(prior["width"]) * 1.12:
            bb_state = "EXPANDING"
        elif prior.get("available") and width < float(prior["width"]) * 0.88:
            bb_state = "CONTRACTING"
        if price >= float(bb["upper"]):
            bb_state = "UPPER_BAND_TOUCH"
        elif price <= float(bb["lower"]):
            bb_state = "LOWER_BAND_TOUCH"

    return {
        "chart_pattern": chart_pattern,
        "pattern_direction": pattern_direction,
        "pattern_confirmed": pattern_confirmed,
        "neckline": round(neckline, 4) if neckline is not None else None,
        "candle_pattern": candle_signal,
        "breakout_retest": breakout_retest,
        "breakout_level": round(breakout_level, 4) if breakout_level is not None else None,
        "fibonacci_confluence": fib_confluence,
        "fibonacci_level": fib_level,
        "fibonacci_direction": fib.get("direction", "NEUTRAL"),
        "bollinger": {k: round(float(v), 6) for k, v in bb.items() if k in {"upper", "middle", "lower", "width", "position"}} if bb.get("available") else {"available": False},
        "bollinger_state": bb_state,
    }


def _classic_trade(candles: list[dict[str, Any]], levels: dict[str, Any]) -> dict[str, Any]:
    """Book-enhanced deterministic Classic Trade engine + shared AI advisory.

    The book rules are confirmations, not standalone triggers. Signals require
    multi-factor agreement and a structurally valid target; otherwise WAIT is
    returned instead of inventing an entry.
    """
    if len(candles) < 60:
        return {"signal": "WAIT", "confidence": 0, "score": 0, "reason": "Classic Trade uchun candle yetarli emas"}

    closes = [float(c["close"]) for c in candles]
    cur = candles[-2]
    prev = candles[-3]
    price = float(cur["close"])
    r = rsi(candles)
    a = max(atr(candles), 1e-9)
    ema20 = _ema(closes[-80:], 20)
    ema50 = _ema(closes[-120:], 50)
    macd = _macd_snapshot(closes)
    regime = _adaptive_regime(candles)
    structure = _structure_state(candles)
    book = _classic_book_patterns(candles, a)

    score = 0
    reasons: list[str] = []
    confirmations = 0

    trend = "BULLISH" if ema20 > ema50 and price > ema20 else "BEARISH" if ema20 < ema50 and price < ema20 else "MIXED"
    if trend == "BULLISH":
        score += 2; confirmations += 1; reasons.append("EMA20 > EMA50 + price above EMA20")
    elif trend == "BEARISH":
        score -= 2; confirmations += 1; reasons.append("EMA20 < EMA50 + price below EMA20")

    if structure.get("prior_structure") == "BULLISH" or structure.get("bos") == "BULLISH" or structure.get("choch") == "BULLISH":
        score += 2; confirmations += 1; reasons.append("bullish market structure/BOS-CHOCH")
    elif structure.get("prior_structure") == "BEARISH" or structure.get("bos") == "BEARISH" or structure.get("choch") == "BEARISH":
        score -= 2; confirmations += 1; reasons.append("bearish market structure/BOS-CHOCH")

    if price >= float(levels["pivot"]):
        score += 1; reasons.append("price above Pivot")
    else:
        score -= 1; reasons.append("price below Pivot")

    if 52 <= r <= 68:
        score += 1; confirmations += 1; reasons.append("RSI bullish confirmation")
    elif 32 <= r <= 48:
        score -= 1; confirmations += 1; reasons.append("RSI bearish confirmation")

    macd_state = str(macd["state"])
    if macd_state in {"BULLISH", "STRONG_BULLISH"}:
        score += 1; confirmations += 1; reasons.append("MACD bullish")
    elif macd_state in {"BEARISH", "STRONG_BEARISH"}:
        score -= 1; confirmations += 1; reasons.append("MACD bearish")

    if book["candle_pattern"] in {"HAMMER", "BULLISH ENGULFING"}:
        score += 1; reasons.append(book["candle_pattern"].lower() + " rejection confirmation")
    elif book["candle_pattern"] == "SHOOTING STAR":
        score -= 1; reasons.append("shooting star rejection confirmation")

    if book["chart_pattern"] == "DOUBLE BOTTOM CONFIRMED":
        score += 3; confirmations += 1; reasons.append("double bottom breakout confirmed")
    elif book["chart_pattern"] == "TRIPLE BOTTOM CONFIRMED":
        score += 4; confirmations += 1; reasons.append("triple bottom breakout confirmed")
    elif book["chart_pattern"] == "DOUBLE TOP CONFIRMED":
        score -= 3; confirmations += 1; reasons.append("double top breakdown confirmed")
    elif book["chart_pattern"] == "TRIPLE TOP CONFIRMED":
        score -= 4; confirmations += 1; reasons.append("triple top breakdown confirmed")

    if book["breakout_retest"] == "BULLISH_BREAKOUT_RETEST":
        score += 2; confirmations += 1; reasons.append("bullish breakout + retest")
    elif book["breakout_retest"] == "BEARISH_BREAKOUT_RETEST":
        score -= 2; confirmations += 1; reasons.append("bearish breakout + retest")

    if book["fibonacci_confluence"]:
        if book["fibonacci_direction"] == "BULLISH":
            score += 1; reasons.append(f"Fib {book['fibonacci_level']} bullish confluence")
        elif book["fibonacci_direction"] == "BEARISH":
            score -= 1; reasons.append(f"Fib {book['fibonacci_level']} bearish confluence")

    if book["bollinger_state"] == "LOWER_BAND_TOUCH" and r < 50:
        score += 1; reasons.append("lower Bollinger context")
    elif book["bollinger_state"] == "UPPER_BAND_TOUCH" and r > 50:
        score -= 1; reasons.append("upper Bollinger context")

    direction = "BUY" if score >= 7 and confirmations >= 4 else "SELL" if score <= -7 and confirmations >= 4 else "WAIT"
    if direction == "BUY" and regime["regime"] == "TRENDING_DOWN":
        direction = "WAIT"; reasons.append("adaptive regime conflict")
    if direction == "SELL" and regime["regime"] == "TRENDING_UP":
        direction = "WAIT"; reasons.append("adaptive regime conflict")

    # Build structural targets from actual levels/swing extremes. AutoTrade later
    # requires RR >= 1.50, so Classic Trade refuses entries that cannot produce
    # a clean >=1.50R target rather than forcing TP geometry.
    highs, lows = _swing_points(candles, 2, 2)
    recent_highs = [x[1] for x in highs[-8:]]
    recent_lows = [x[1] for x in lows[-8:]]
    if direction == "BUY":
        supports = [float(levels["s1"]), *recent_lows]
        support = max([x for x in supports if x < price] or [price - a])
        sl = round(support - max(a * 0.20, 0.10), 2)
        risk = price - sl
        targets = sorted(set([float(levels["r1"]), float(levels["r2"]), float(levels["r3"]), *[x for x in recent_highs if x > price]]))
        targets = [x for x in targets if x > price and (x - price) / max(risk, 1e-9) >= 1.50]
        if not targets:
            direction = "WAIT"; reasons.append("No structural BUY target with RR >= 1.50")
            sl = None; tp = []
        else:
            tp = [round(targets[0], 2)]
            if len(targets) > 1: tp.append(round(targets[1], 2))
    elif direction == "SELL":
        resistances = [float(levels["r1"]), *recent_highs]
        resistance = min([x for x in resistances if x > price] or [price + a])
        sl = round(resistance + max(a * 0.20, 0.10), 2)
        risk = sl - price
        targets = sorted(set([float(levels["s1"]), float(levels["s2"]), float(levels["s3"]), *[x for x in recent_lows if x < price]], reverse=True))
        targets = [x for x in targets if x < price and (price - x) / max(risk, 1e-9) >= 1.50]
        if not targets:
            direction = "WAIT"; reasons.append("No structural SELL target with RR >= 1.50")
            sl = None; tp = []
        else:
            tp = [round(targets[0], 2)]
            if len(targets) > 1: tp.append(round(targets[1], 2))
    else:
        sl = None; tp = []

    confidence = int(min(97, max(0, 50 + abs(score) * 5 + confirmations * 4 + (5 if book["chart_pattern"] != "NONE" else 0))))
    quality = int(max(0, min(100, confidence + (8 if abs(score) >= 9 else 0) + (5 if regime["trend_strength"] >= 65 else 0))))
    return {
        "signal": direction,
        "confidence": confidence,
        "score": score,
        "confirmations": confirmations,
        "entry": round(price, 2) if direction in {"BUY", "SELL"} else None,
        "stop_loss": sl,
        "take_profit": tp,
        "trend": trend,
        "rsi": round(r, 2),
        "rsi_state": "OVERBOUGHT" if r >= 70 else "OVERSOLD" if r <= 30 else "NEUTRAL",
        "ema20": round(ema20, 2),
        "ema50": round(ema50, 2),
        "macd": round(float(macd["line"]), 6),
        "macd_signal": round(float(macd["signal"]), 6),
        "macd_histogram": round(float(macd["histogram"]), 6),
        "macd_state": macd_state,
        "pattern": book["candle_pattern"] if book["candle_pattern"] != "NONE" else book["chart_pattern"],
        "book_pattern": book["chart_pattern"],
        "breakout_retest": book["breakout_retest"],
        "fibonacci_confluence": book["fibonacci_confluence"],
        "fibonacci_level": book["fibonacci_level"],
        "bollinger_state": book["bollinger_state"],
        "bollinger": book["bollinger"],
        "pivot": levels["pivot"],
        "support": [levels["s1"], levels["s2"], levels["s3"]],
        "resistance": [levels["r1"], levels["r2"], levels["r3"]],
        "reason": "; ".join(reasons),
        "method": "Classic · Book-Enhanced Multi-Factor Confluence",
        "book_sources": [
            "SIMPLE TRADING Book v1: double/triple top & bottom",
            "XAU/USD Multi-Factor Technical Analysis: MA/RSI/MACD/BB/ATR/Pivot/S-R/BOS/CHOCH/breakout-retest",
            "ICT Trading Strategy: market-structure confirmation concepts",
            "Fibonacci strategy: retracement confluence"
        ],
        "market_regime": regime,
        "structure": structure,
        "strategy_engine": "Book-Enhanced Classic Strategy V3",
        "strategy_version": "V3-BOOK-ENHANCED",
        "strategy_quality": quality,
        "decision_state": "CONFIRMED" if direction in {"BUY", "SELL"} else "WAIT"
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
    """AI analysis with candle-level cache and request coalescing.

    The shared multi-provider router is used instead of binding this module to one
    vendor. Live AI results are cached for the candle; provider failures use only a
    short cache so the network can recover and automatically switch back.
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
            if cached_candle == str(candle_time):
                cached_ttl = AI_FAILURE_CACHE_TTL if cached_result.get("_failure_cache") else AI_CACHE_TTL
                if now - cached_at < cached_ttl:
                    out = dict(cached_result)
                    out.pop("_failure_cache", None)
                    return out

        prompt = (
            "You are a disciplined market-analysis assistant. Based ONLY on the supplied XAU/USD technical context, "
            "give a concise non-guaranteed trading analysis. Return JSON with keys: summary, bias, confidence, advice. "
            "Confidence must be an integer 0-100. Do not claim certainty or guaranteed profits.\n\n"
            + json.dumps(analysis_context, ensure_ascii=False, default=str)
        )
        if any((GROQ_API_KEY, GROQ_API_KEY_2, GEMINI_API_KEY, OPENROUTER_API_KEY, MISTRAL_API_KEY, CEREBRAS_API_KEY,
                CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN, DEEPSEEK_API_KEY, OPENAI_API_KEY, HF_TOKEN)):
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
                result = {
                    "mode": "fallback",
                    "warning": f"AI network unavailable: {msg}",
                    "summary": "Barcha ulangan AI providerlar vaqtincha javob bermadi; tizim keyingi so‘rovda avtomatik qayta urinadi.",
                    "bias": analysis_context.get("bias", "NEUTRAL"),
                    "confidence": 0,
                    "advice": "AI tarmog‘i avtomatik ravishda keyingi ishlayotgan providerga o‘tadi."
                }
                AI_CACHE[cache_key] = (now, str(candle_time), {**result, "_failure_cache": True})
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
        if cached and cached[1] == str(candle_time):
            cached_ttl = AI_FAILURE_CACHE_TTL if cached[2].get("_failure_cache") else AI_CACHE_TTL
            if now-cached[0] < cached_ttl:
                cached_result = dict(cached[2])
                cached_result.pop("_failure_cache", None)
                return cached_result
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
        if any((GROQ_API_KEY, GROQ_API_KEY_2, GEMINI_API_KEY, OPENROUTER_API_KEY, MISTRAL_API_KEY, CEREBRAS_API_KEY,
                CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN, DEEPSEEK_API_KEY, OPENAI_API_KEY, HF_TOKEN)):
            try:
                if source.strip().lower() == "fibonacci":
                    prompt=("You are the STRICT AI validation layer for SignalX's Fibonacci strategy. "
                        "Use only the supplied deterministic Fibonacci/Fibo Musang analysis. The source concepts include standard retracement levels "
                        "(23.6, 38.2, 50, 61.8, 78.6), extensions/projections, Fibonacci price clusters/FibZones, relevant swing selection, "
                        "Fibo Musang CBR/Initial Break/Dominant Candle/nearest SNR break, 261/423 cycle references, 50% Pin Bar/price-action confirmation, "
                        "Fibonacci + trendline/SR confluence, higher-timeframe filtering, and a volatility/data-quality guard. "
                        "Return JSON only with: signal (BUY/SELL/WAIT), confidence (0-100 integer), agreement (0-100 integer), "
                        "validation (true/false), risk_flags (array of short strings), reasoning (short string). "
                        "Do not invent market data, news, levels, or Fibonacci anchors. Do not add unrelated indicators or strategies. "
                        "validation=true only when the deterministic signal is BUY/SELL, the Fibonacci evidence is coherent, geometry and RR are valid, "
                        "and there is no major conflict. If evidence is incomplete/conflicting, return WAIT and validation=false.\n\n"+json.dumps(context,ensure_ascii=False,default=str))
                elif source.strip().lower() == "algo/smc":
                    prompt=("You are the STRICT AI validation layer for SignalX's Algo/SMC strategy, derived only from the supplied trading-book concepts. "
                        "Evaluate ONLY the supplied deterministic analysis. Do not invent prices, liquidity, news, or structure. "
                        "The book concepts include liquidity-first analysis, daily/weekly/HTF cycles, accumulation-manipulation-distribution (AMD), "
                        "money transfer, strong/weak highs and lows, premium/discount, fake market-structure breaks, algo candles, FVG/inefficiency, "
                        "order block/breaker/rejection block, top-down analysis, and one-minute/Ping-Pong timing. "
                        "Return JSON only with: signal (BUY/SELL/WAIT), confidence (0-100 integer), agreement (0-100 integer), "
                        "validation (true/false), risk_flags (array of short strings), reasoning (short string). "
                        "Be strict: validation=true only when the deterministic setup is coherent, the direction agrees with the supplied HTF storyline, "
                        "and there is no obvious fake-break/roadblock risk. If evidence conflicts or the setup is incomplete, return WAIT and validation=false. "
                        "This is analysis, not a guarantee.\n\n"+json.dumps(context,ensure_ascii=False,default=str))
                else:
                    prompt=("You are the validation layer of a quantitative XAU/USD trading system. "
                        "Evaluate ONLY the supplied deterministic analysis. Do not invent prices or external news. "
                        "Return JSON only: signal (BUY/SELL/WAIT), confidence (0-100 integer), agreement (0-100 integer), "
                        "risk_flags (array of short strings), reasoning (short string). "
                        "Be conservative: if evidence conflicts or the setup is weak, return WAIT. "
                        "This is analysis, not a guarantee.\n\n"+json.dumps(context,ensure_ascii=False,default=str))
                text, ai_provider = await ai_json_completion(prompt)
                parsed=json.loads(text)
                sig=str(parsed.get("signal","WAIT")).upper()
                conf=max(0,min(100,int(parsed.get("confidence",0))))
                agreement=max(0,min(100,int(parsed.get("agreement",0))))
                risk_flags=parsed.get("risk_flags",[]) if isinstance(parsed.get("risk_flags",[]),list) else []
                validation=bool(parsed.get("validation", sig==base_signal and conf>=85 and agreement>=70))
                if source.strip().lower() == "algo/smc":
                    validation=bool(validation and sig==base_signal and conf>=85 and agreement>=70)
                result={"mode":ai_provider,"signal":sig if sig in {"BUY","SELL","WAIT"} else "WAIT",
                        "confidence":conf,"agreement":agreement,"validation":validation,
                        "risk_flags":risk_flags,"reasoning":str(parsed.get("reasoning","AI validation."))}
            except Exception as exc:
                msg=str(exc)
                result={"mode":"fallback","signal":base_signal if base_signal in {"BUY","SELL"} else "WAIT",
                        "confidence":int(deterministic.get("confidence",0) or 0),"agreement":50,
                        "risk_flags":["AI network unavailable"],"reasoning":"All configured AI providers failed; deterministic quantitative validation retained."}
        else:
            result={"mode":"rule_based","signal":base_signal if base_signal in {"BUY","SELL"} else "WAIT",
                    "confidence":int(deterministic.get("confidence",0) or 0),"agreement":50,
                    "risk_flags":[],"reasoning":"AI network unavailable; quantitative engine retained until a provider recovers."}
        if result.get("mode") in {"fallback", "rule_based", "unavailable"}:
            # Do not lock the module to a failed AI network for an entire candle.
            AI_SIGNAL_CACHE[key]=(now,str(candle_time),{**result, "_failure_cache": True})
        else:
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


def _smart_module_gate(item: dict[str, Any], ai: dict[str, Any], candles: list[dict[str, Any]], direction: str) -> dict[str, Any]:
    """Cross-module AI + market-structure quality gate for AutoTrade.

    The gate is intentionally independent of RR and TP2. It protects execution by
    requiring directional AI agreement, reasonable AI confidence/agreement, and no
    obvious regime/structure conflict. If the AI provider is unavailable, the
    deterministic engine remains usable but still has to pass the execution risk gate.
    """
    direction = str(direction or "WAIT").upper()
    ai_signal = str(ai.get("signal") or "WAIT").upper()
    ai_conf = int(ai.get("confidence") or 0)
    ai_agree = int(ai.get("agreement") or 0)
    mode = str(ai.get("mode") or "fallback")
    deterministic_conf = int(item.get("confidence") or item.get("strategy_quality") or item.get("trend_power") or item.get("score") or 0)
    reasons=[]
    checks=[]

    def add(name: str, ok: bool, reason: str):
        checks.append({"name":name,"status":"PASS" if ok else "MISS"})
        if ok: reasons.append(reason)

    if direction not in {"BUY","SELL"}:
        return {"ok":False,"state":"WAIT","score":0,"checks":checks,"reason":"NO_DIRECTION"}

    # Deterministic regime/structure check. This is separate from RR.
    regime = item.get("market_regime") if isinstance(item.get("market_regime"), dict) else _adaptive_regime(candles)
    regime_name = str((regime or {}).get("regime") or "RANGE")
    regime_conflict = (direction=="BUY" and regime_name=="TRENDING_DOWN") or (direction=="SELL" and regime_name=="TRENDING_UP")
    add("Market Regime", not regime_conflict, f"regime={regime_name}")

    try:
        structure=_structure_state(candles)
    except Exception:
        structure={}
    struct_dir = "BUY" if structure.get("bos")=="BULLISH" or structure.get("choch")=="BULLISH" else "SELL" if structure.get("bos")=="BEARISH" or structure.get("choch")=="BEARISH" else "WAIT"
    strong_opposite = (direction=="BUY" and structure.get("prior_structure")=="BEARISH" and struct_dir!="BUY") or (direction=="SELL" and structure.get("prior_structure")=="BULLISH" and struct_dir!="SELL")
    add("Structure", not strong_opposite, f"structure={structure.get('prior_structure','MIXED')}/{struct_dir}")

    # Real AI providers are a hard validation layer; deterministic fallback is not
    # falsely presented as live AI. In fallback mode, deterministic quality remains the gate.
    live_ai = mode not in {"fallback","rule_based"}
    if live_ai:
        ai_ok = ai_signal == direction and ai_conf >= 65 and ai_agree >= 55
        add("AI Direction", ai_signal==direction, f"AI={ai_signal}")
        add("AI Confidence", ai_conf>=65, f"AI confidence={ai_conf}%")
        add("AI Agreement", ai_agree>=55, f"AI agreement={ai_agree}%")
    else:
        ai_ok = True
        add("AI Availability", True, f"AI mode={mode}; deterministic fallback retained")

    det_ok = deterministic_conf >= 60
    add("Deterministic Quality", det_ok, f"deterministic quality={deterministic_conf}")
    ok = (not regime_conflict) and (not strong_opposite) and ai_ok and det_ok
    # A provider-unavailable fallback is allowed only because the independent
    # execution gate below still enforces geometry, valid TP1 and maximum SL risk.
    score = round((deterministic_conf*0.45) + (ai_conf*0.35 if live_ai else deterministic_conf*0.20) + (ai_agree*0.20 if live_ai else 20))
    return {"ok":ok,"state":"READY" if ok else "AI_VALIDATION_FAILED","score":max(0,min(100,score)),
            "ai_live":live_ai,"ai_signal":ai_signal,"ai_confidence":ai_conf,"ai_agreement":ai_agree,
            "deterministic_quality":deterministic_conf,"market_regime":regime,"structure":structure,
            "checks":checks,"reason":"; ".join(reasons) if ok else "AI/market quality validation failed"}


async def _module_ai_advisory(source: str, symbol: str, interval: str, candle_time: Any, module_result: dict[str, Any]) -> dict[str, Any]:
    """Shared AI advisory for individual dashboard modules.
    It assists analysis but never acts as an AutoTrade quality gate.
    """
    ai = await ai_validate_module_signal(source, symbol, interval, candle_time, module_result)
    return {"enabled": True, "mode": ai.get("mode", "rule_based"),
            "signal": ai.get("signal", "WAIT"), "confidence": ai.get("confidence", 0),
            "agreement": ai.get("agreement", 50), "risk_flags": ai.get("risk_flags", []),
            "reasoning": ai.get("reasoning", "Shared AI advisory."),
            "role": "analysis_advisory_only", "autotrade_gate": False}


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




def build_advanced_signal(candles: list[dict[str, Any]], interval: str, news_blocked: bool=False) -> dict[str, Any]:
    """Legacy quantitative signal shell with NO legacy SNR source.

    Active signal context here is limited to structure, liquidity, OB, FVG, trendline,
    Fibonacci, momentum and regime. Malaysian SNR lives only inside MSAI Strategy.
    """
    current=float(candles[-1]["close"])
    avtr=max(atr(candles), current*0.0004)
    structure=_structure_state(candles)
    fvg=_detect_fvg(candles)
    ob=_detect_order_block(candles,avtr)
    highs,lows=_swing_points(candles)
    trendline=_trendline_analysis(candles)
    fibonacci=_fibonacci_analysis(candles)
    liq=_detect_liquidity(candles,highs,lows)
    closes=[float(c["close"]) for c in candles]
    trend_slope=_linear_slope(closes[-50:])
    global_slope=_linear_slope(closes[-200:] if len(closes)>=200 else closes)
    trend="BULLISH" if trend_slope>0 else "BEARISH" if trend_slope<0 else "NEUTRAL"
    global_trend="BULLISH" if global_slope>0 else "BEARISH" if global_slope<0 else "NEUTRAL"
    r=rsi(candles)
    score=0; reasons=[]
    if liq["type"]=="SELL_SIDE_SWEEP": score+=2; reasons.append("sell-side liquidity sweep")
    elif liq["type"]=="BUY_SIDE_SWEEP": score-=2; reasons.append("buy-side liquidity sweep")
    if ob["type"]=="BULLISH": score+=1; reasons.append("bullish order block")
    elif ob["type"]=="BEARISH": score-=1; reasons.append("bearish order block")
    if fvg["type"]=="BULLISH": score+=1; reasons.append("bullish FVG")
    elif fvg["type"]=="BEARISH": score-=1; reasons.append("bearish FVG")
    if structure["bos"]=="BULLISH": score+=2; reasons.append("BOS bullish")
    elif structure["bos"]=="BEARISH": score-=2; reasons.append("BOS bearish")
    if structure["choch"]=="BULLISH": score+=2; reasons.append("CHOCH bullish")
    elif structure["choch"]=="BEARISH": score-=2; reasons.append("CHOCH bearish")
    if structure["internal_structure"]=="BULLISH": score+=1
    elif structure["internal_structure"]=="BEARISH": score-=1
    if trend=="BULLISH": score+=2; reasons.append("local trend bullish")
    elif trend=="BEARISH": score-=2; reasons.append("local trend bearish")
    if global_trend=="BULLISH": score+=2; reasons.append("global trend bullish")
    elif global_trend=="BEARISH": score-=2; reasons.append("global trend bearish")
    if r>=55: score+=1
    elif r<=45: score-=1
    if trendline.get("trend")=="BULLISH": score+=2; reasons.append("bullish trend line")
    elif trendline.get("trend")=="BEARISH": score-=2; reasons.append("bearish trend line")
    if trendline.get("signal")=="BUY": score+=1; reasons.append("trend line buy confirmation")
    elif trendline.get("signal")=="SELL": score-=1; reasons.append("trend line sell confirmation")
    direction="BUY" if score>=7 else "SELL" if score<=-7 else "WAIT"
    if direction=="BUY" and trend!="BULLISH": direction="WAIT"; reasons.append("WAIT: local trend conflict")
    if direction=="SELL" and trend!="BEARISH": direction="WAIT"; reasons.append("WAIT: local trend conflict")
    if direction=="BUY" and global_trend!="BULLISH": direction="WAIT"; reasons.append("WAIT: global trend conflict")
    if direction=="SELL" and global_trend!="BEARISH": direction="WAIT"; reasons.append("WAIT: global trend conflict")
    if direction=="BUY" and trendline.get("trend")=="BEARISH": direction="WAIT"; reasons.append("WAIT: trend line conflict")
    if direction=="SELL" and trendline.get("trend")=="BULLISH": direction="WAIT"; reasons.append("WAIT: trend line conflict")
    if direction=="BUY" and fibonacci.get("direction")=="BEARISH": direction="WAIT"; reasons.append("WAIT: Fibonacci conflict")
    if direction=="SELL" and fibonacci.get("direction")=="BULLISH": direction="WAIT"; reasons.append("WAIT: Fibonacci conflict")
    if news_blocked: direction="WAIT"; reasons.append("WAIT: news blackout")
    entry=current
    swing_low=structure["swing_low"]; swing_high=structure["swing_high"]
    if direction=="BUY":
        sl=min(swing_low, current-avtr*1.2); risk=max(entry-sl,avtr*0.6); tp=[entry+risk*1.5,entry+risk*2.5]
    elif direction=="SELL":
        sl=max(swing_high, current+avtr*1.2); risk=max(sl-entry,avtr*0.6); tp=[entry-risk*1.5,entry-risk*2.5]
    else: sl=None; tp=[]
    rr=(abs((tp[0]-entry)/(entry-sl)) if direction=="BUY" and sl is not None else abs((entry-tp[0])/(sl-entry)) if direction=="SELL" and sl is not None else 0.0)
    confirmations=sum([
        1 if (direction=="BUY" and liq["type"]=="SELL_SIDE_SWEEP") or (direction=="SELL" and liq["type"]=="BUY_SIDE_SWEEP") else 0,
        1 if (direction=="BUY" and ob["type"]=="BULLISH") or (direction=="SELL" and ob["type"]=="BEARISH") else 0,
        1 if (direction=="BUY" and fvg["type"]=="BULLISH") or (direction=="SELL" and fvg["type"]=="BEARISH") else 0,
        1 if (direction=="BUY" and structure["bos"]=="BULLISH") or (direction=="SELL" and structure["bos"]=="BEARISH") else 0,
        1 if (direction=="BUY" and trend=="BULLISH") or (direction=="SELL" and trend=="BEARISH") else 0,
        1 if (direction=="BUY" and global_trend=="BULLISH") or (direction=="SELL" and global_trend=="BEARISH") else 0,
        1 if (direction=="BUY" and trendline.get("trend")=="BULLISH") or (direction=="SELL" and trendline.get("trend")=="BEARISH") else 0,
        1 if (direction=="BUY" and trendline.get("signal")=="BUY") or (direction=="SELL" and trendline.get("signal")=="SELL") else 0,
    ]) if direction!="WAIT" else 0
    confidence=min(99,max(35,50+abs(score)*5+confirmations*3))
    setup="ULTRA_CONFLUENCE" if direction!="WAIT" and confirmations>=5 and rr>=1.5 else ("CONFLUENCE" if direction!="WAIT" else "WAIT_CONFLUENCE")
    quality="A+" if direction!="WAIT" and confidence>=90 and confirmations>=5 and rr>=1.5 else "A" if direction!="WAIT" else "WAIT"
    result={
        "interval":interval,"signal":direction,"entry":round(entry,4),"stop_loss":round(sl,4) if sl is not None else None,
        "take_profit":[round(x,4) for x in tp],"confidence":confidence,"score":score,"setup":setup,
        "components":{"ICT":structure["internal_structure"],"Order Block":ob,"FVG":fvg,"Liquidity":liq,
                       "Trend Line":trendline,"Fibonacci":fibonacci,"Trend":trend,"Global Trend Line":global_trend,
                       "BOS":structure["bos"],"CHOCH":structure["choch"],"Internal Structure":structure["internal_structure"]},
        "trendline":trendline,"fibonacci":fibonacci,"risk_reward":round(rr,2),"confirmations":confirmations,"quality_grade":quality,
        "reason":"; ".join(dict.fromkeys(reasons)) or "No strong confluence",
        "rsi":round(r,2),"atr":round(avtr,4),"current_price":round(current,4),
        "evaluated_at":datetime.now(timezone.utc).isoformat()
    }
    return result




async def build_full_analysis(symbol: str, interval: str) -> dict[str, Any]:
    """Build dashboard analysis from the shared market-data snapshot.

    Every market-derived field is calculated from get_candles(), which is backed by
    the canonical multi-provider market router.
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

    # MTF uses the same market router, with one canonical snapshot per timeframe.
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
        "market_regime": _adaptive_regime(candles_data),
        "strategy_layers": ["MTF context","Structure","Liquidity","Trendline","Momentum","Volatility","Scenario validation"],
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



def _ai_qa_local_fallback(context: dict[str, Any], question: str) -> tuple[str, str, float, str]:
    """Useful no-provider fallback based only on already-fetched live context."""
    q=(question or '').lower()
    analysis=context.get('analysis') or {}
    mtf=context.get('mtf') or {}
    direction=str(analysis.get('direction') or mtf.get('overall') or 'NEUTRAL').upper()
    price=context.get('current_price')
    events=context.get('economic_calendar',{}).get('events') or []
    tech=analysis.get('technical') or {}
    levels=analysis.get('levels') or {}
    bits=[]
    if price is not None: bits.append(f"Joriy narx: {price}.")
    bits.append(f"Kontekst bo‘yicha yo‘nalish: {direction}.")
    if tech.get('rsi') is not None: bits.append(f"RSI: {tech.get('rsi')}.")
    if levels.get('pivot') is not None: bits.append(f"Pivot: {levels.get('pivot')}.")
    if events:
        names=[str(e.get('event') or 'event') for e in events[:5]]
        bits.append(f"Yaqin economic calendar’da {len(events)} ta event bor; muhimlari: {', '.join(names)}.")
    elif 'news' in q or 'fomc' in q:
        bits.append("Hozir live economic-event manbasi bo‘yicha tasdiqlangan event olinmadi, shuning uchun aniq news/FOMC faktini uydirmayman.")
    if 'trend' in q or 'xauusd' in q or 'eurusd' in q or 'kecha' in q:
        answer=' '.join(bits)+" Bu providerlarsiz ishlaydigan context fallback; tarixiy kun taqqoslash uchun to‘liq candle tarixini alohida tekshirish kerak."
    elif 'fomc' in q:
        answer=' '.join(bits)+" FOMC uchun asosiy scenario: event oldidan volatility oshishi mumkin; bullish yoki bearish yo‘nalishni fakt sifatida emas, shartli scenario sifatida baholash kerak."
    else:
        answer=' '.join(bits)+" AI provider javob bermasa, tizim faqat mavjud live context asosida xavfsiz fallback beradi."
    return answer, direction if direction in {'BUY','SELL','BULLISH','BEARISH'} else 'NEUTRAL', 0.0, 'AI provider unavailable; context-only fallback.'

@app.post("/api/v1/ai/chat")
async def ai_chat(body: AIChatBody, authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    user = current_user(authorization, session)
    ok, retry_after = _ai_qa_rate_ok(int(user.id))
    if not ok:
        raise HTTPException(status_code=429, detail=f"AI Q&A limiti tugadi. {retry_after} soniyadan keyin qayta urinib ko‘ring.")
    symbol = clean_symbol(body.symbol)
    interval = validate_interval(body.interval)
    question = body.question.strip()
    context = await build_ai_qa_context(symbol, interval)
    prompt = f"""
You are SignalX AI Q&A, a trading-analysis assistant for XAU/USD and EUR/USD.
Answer the user's question in Uzbek unless the user asks for another language.
Use ONLY the supplied live context and clearly say when data is unavailable.
Never invent current news, prices, FOMC dates, economic events, or indicator readings.
For questions such as today's/ yesterday's trend, explain the observed evidence from the context.
For FOMC/news questions, distinguish scheduled events from market interpretation.
For trade ideas, provide scenario-based levels/conditions only when supported by context; never promise profit or certainty.
Do not place or execute trades and do not change AutoTrade settings.
Mention that an idea is not a guarantee when the user asks for a trading idea.
Return strict JSON with keys: answer, bias, confidence, risk_note.
answer should be concise but useful, with short headings when appropriate.

CURRENT CONTEXT:
{json.dumps(context, ensure_ascii=False, default=str)}

USER QUESTION:
{question}
"""
    try:
        raw, provider = await ai_json_completion(prompt)
        parsed = _ai_qa_extract_answer(raw)
        return {
            "ok": True,
            "provider": provider,
            "symbol": symbol,
            "interval": interval,
            "answer": parsed["answer"],
            "bias": parsed["bias"],
            "confidence": max(0.0, min(100.0, parsed["confidence"])),
            "risk_note": parsed["risk_note"],
            "context": {
                "as_of_utc": context["as_of_utc"],
                "quote_source": context.get("quote_source"),
                "economic_calendar_provider": context.get("economic_calendar", {}).get("provider"),
                "economic_events_count": len(context.get("economic_calendar", {}).get("events") or []),
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        # Do not leak provider credentials/details. Return a useful safe fallback.
        mtf = context.get("mtf") or {}
        direction = str((context.get("analysis") or {}).get("direction") or mtf.get("overall") or "NEUTRAL").upper()
        events = context.get("economic_calendar", {}).get("events") or []
        answer, bias, confidence, risk_note = _ai_qa_local_fallback(context, question)
        return {
            "ok": True, "provider": "context-fallback", "symbol": symbol, "interval": interval,
            "answer": answer,
            "bias": bias,
            "confidence": confidence,
            "risk_note": risk_note,
            "context": {
                "as_of_utc": context["as_of_utc"],
                "quote_source": context.get("quote_source"),
                "economic_calendar_provider": context.get("economic_calendar", {}).get("provider"),
                "economic_events_count": len(context.get("economic_calendar", {}).get("events") or []),
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "ai_provider_error": str(exc)[:240],
        }

@app.get("/api/v1/candles/{symbol:path}")
async def candles_endpoint(symbol: str, interval: str = Query(DEFAULT_INTERVAL), limit: int = Query(220, ge=2, le=500)) -> dict[str, Any]:
    """Canonical candle endpoint backed by the shared market-data failover router."""
    interval = validate_interval(interval)
    try:
        snapshot = await get_market_snapshot(clean_symbol(symbol), interval, limit)
        return {
            "ok": True,
            "symbol": snapshot["symbol"],
            "interval": interval,
            "mode": "live",
            "provider": snapshot["provider_name"],
            "provider_id": snapshot["provider"],
            "source": tv_symbol_for(symbol) if snapshot["provider"] == "tradingview" else snapshot["provider_name"],
            "current_price": round(float(snapshot["current_price"]), 4),
            "candles": snapshot["candles"],
            "candle": snapshot["candle"],
            "warning": snapshot.get("warning"),
            "provider_errors": snapshot.get("provider_errors", []),
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Market data unavailable: {exc}")


@app.get("/api/v1/quote/{symbol:path}")
async def quote(symbol: str, interval: str = Query(DEFAULT_INTERVAL)) -> dict[str, Any]:
    """Quote from the exact market snapshot used by strategy calculations."""
    symbol = clean_symbol(symbol)
    interval = validate_interval(interval)
    try:
        snapshot = await get_market_snapshot(symbol, interval, 80)
        ts = int(snapshot["candle"]["time"])
        return {
            "symbol": symbol, "price": round(float(snapshot["current_price"]), 4), "mode": "live",
            "provider": snapshot["provider_name"], "provider_id": snapshot["provider"],
            "timestamp": datetime.fromtimestamp(ts, timezone.utc).isoformat(),
            "source": tv_symbol_for(symbol) if snapshot["provider"] == "tradingview" else snapshot["provider_name"],
            "warning": snapshot.get("warning"),
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Market data quote unavailable: " + str(exc))


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


async def build_msai_strategy(symbol: str, selected: str) -> dict[str, Any]:
    """SIGNALX MSAI Strategy v1.0: Malaysian SNR + Price Action + MTF + AI validation.

    The deterministic layer follows the uploaded Malaysian SNR manual's vocabulary:
    HTF storyline, fresh SNR, wick touch/rejection, liquidity sweep/MISS, engulfing,
    trendline/SNR confluence, QML/HNS, LTF breakout/retest and roadblock awareness.
    AI is a confirmation gate, not a replacement for the deterministic price-action rules.
    """
    cache_key = f"{clean_symbol(symbol)}|{selected}"
    now_mono = asyncio.get_running_loop().time()
    cached = MSAI_CACHE.get(cache_key)
    if cached and now_mono - cached[0] < MSAI_CACHE_TTL:
        return cached[1]

    key = clean_symbol(symbol)
    # The book's storyline uses Weekly as the main direction and Daily/H4/H1 for
    # confirmation/roadblocks. Weekly is synthesized from the available Daily series.
    tf_list = ["1min", "5min", "15min", "30min", "1h", "4h", "1day"]
    raw: dict[str, tuple[list[dict[str, Any]], str, Any]] = {}
    errors: dict[str, str] = {}
    for tf in tf_list:
        try:
            data = await get_candles(key, tf, 180 if tf != "1min" else 220)
            raw[tf] = data
        except Exception as exc:
            errors[tf] = f"{type(exc).__name__}: {exc}"

    selected_candles = raw.get(selected, ([], "error", None))[0]
    if len(selected_candles) < 50:
        raise MarketDataError(f"MSAI uchun {selected} timeframe candle yetarli emas")

    mtf_rows: dict[str, dict[str, Any]] = {}
    for tf, pack in raw.items():
        candles = pack[0]
        if len(candles) >= 20:
            mtf_rows[tf] = {
                "trend": direction_from_candles(candles),
                "price": round(float(candles[-1]["close"]), 5),
            }
    daily = raw.get("1day", ([], "error", None))[0]
    weekly = aggregate_weekly(daily)
    if weekly:
        mtf_rows["1week"] = {
            "trend": direction_from_candles(weekly),
            "price": round(float(weekly[-1]["close"]), 5),
        }

    summary_input = {k: v for k, v in mtf_rows.items() if k != "1week"}
    summary = summarize_mtf(summary_input)
    weekly_bias = mtf_rows.get("1week", {}).get("trend", "NEUTRAL")
    daily_bias = mtf_rows.get("1day", {}).get("trend", "NEUTRAL")
    h4_bias = mtf_rows.get("4h", {}).get("trend", "NEUTRAL")
    h1_bias = mtf_rows.get("1h", {}).get("trend", "NEUTRAL")
    # Book-faithful storyline gate: the higher timeframe has to point the same way
    # as the setup, and a Daily counter-story is treated as a roadblock rather than ignored.
    direction_bias = summary.get("direction_bias", "NEUTRAL")
    storyline_alignment = bool(
        direction_bias in {"BULLISH", "BEARISH"}
        and weekly_bias in {"NEUTRAL", direction_bias}
        and daily_bias in {"NEUTRAL", direction_bias}
    )
    summary["weekly_trend"] = weekly_bias
    summary["daily_trend"] = daily_bias
    summary["h4_trend"] = h4_bias
    summary["h1_trend"] = h1_bias
    summary["alignment"] = storyline_alignment
    summary["direction_bias"] = direction_bias

    # Use the selected timeframe as the local execution chart. The book's 2-TF rule
    # is applied to the closest lower timeframe when one exists.
    lower_map = {"1day":"1h", "4h":"30min", "1h":"15min", "30min":"5min", "15min":"5min", "5min":"1min", "1min":"1min"}
    lower_tf = lower_map.get(selected, "5min")
    local_mtf = {"direction_bias": direction_bias, "alignment": storyline_alignment}
    base = analyze_msai(selected_candles, local_mtf, selected)
    base["storyline"] = summary
    base["mtf_timeframes"] = mtf_rows

    lower_candles = raw.get(lower_tf, ([], "error", None))[0]
    two_tf = {"timeframe": lower_tf, "valid": False, "engulfing": {}, "breakout": {}, "retest": False}
    if len(lower_candles) >= 40 and base.get("raw_direction") in {"BUY", "SELL"}:
        from msai_strategy import lower_timeframe_confirmation
        two_tf = lower_timeframe_confirmation(lower_candles, base["raw_direction"])
    base["two_tf_confirmation"] = two_tf

    # If the book-style lower-timeframe confirmation is not available, keep the setup in WAIT.
    if base.get("raw_direction") in {"BUY", "SELL"}:
        base["checks"]["two_tf_confirmation"] = bool(two_tf.get("valid"))
        if not two_tf.get("valid"):
            base["signal"] = "WAIT"
            base["state"] = "WAIT_2TF_CONFIRMATION"
            base["setup"] = "WAIT_2TF_CONFIRMATION"
            base["reason"] = (base.get("reason", "") + "; 2-TF confirmation missing").strip("; ")

    # Hard risk/geometry gate. The book illustrates risk/reward examples; SignalX uses
    # RR >= 1.5 as an implementation threshold, not as a claim that the book specifies 1.5.
    if base.get("signal") in {"BUY", "SELL"} and float(base.get("risk_reward") or 0) < 1.5:
        base["signal"] = "WAIT"
        base["state"] = "WAIT_RR"
        base["setup"] = "WAIT_RR"
        base["reason"] = (base.get("reason", "") + "; RR below SignalX minimum 1.5").strip("; ")

    # AI gate: one structured second-opinion call per symbol/timeframe/candle.
    candle_time = selected_candles[-1].get("time")
    ai_key = f"{key}|{selected}"
    async with MSAI_AI_LOCKS_GUARD:
        ai_lock = MSAI_AI_LOCKS.setdefault(ai_key, asyncio.Lock())
    async with ai_lock:
        ai_now = datetime.now(timezone.utc).timestamp()
        cached_ai = MSAI_AI_CACHE.get(ai_key)
        ai = None
        if cached_ai and cached_ai[1] == candle_time:
            cached_payload = dict(cached_ai[2])
            cached_ttl = AI_FAILURE_CACHE_TTL if cached_payload.get("_failure_cache") else AI_CACHE_TTL
            if ai_now - cached_ai[0] < cached_ttl:
                cached_payload.pop("_failure_cache", None)
                ai = cached_payload
        if ai is None:
            ai = {"signal":"WAIT", "confidence":0, "validation":False,
                  "provider":None, "mode":"unavailable", "reason":"AI network unavailable; no signal emitted.", "risk_flags":[]}
            ai_context = {
                "symbol": key,
                "timeframe": selected,
                "current_price": selected_candles[-1].get("close"),
                "deterministic_signal": base.get("raw_direction", "WAIT"),
                "deterministic_score": base.get("score", 0),
                "deterministic_state": base.get("state"),
                "checks": base.get("checks", {}),
                "snr": base.get("snr", {}),
                "rejection": base.get("rejection", {}),
                "liquidity": base.get("liquidity", {}),
                "engulfing": base.get("engulfing", {}),
                "trendline": base.get("trendline", {}),
                "qml_hns": base.get("qml_hns", {}),
                "breakout": base.get("breakout", {}),
                "two_tf_confirmation": two_tf,
                "storyline": summary,
                "rule": "Use only the supplied Malaysian SNR/Price Action framework. Validate, do not invent. No ICT/FVG/OB/RSI/MACD. Return WAIT when validation is incomplete or context conflicts.",
            }
            try:
                prompt = (
                    "You are the AI validation layer for SIGNALX — MSAI STRATEGY v1.0. "
                    "The strategy is derived from the supplied Malaysian SNR trading manual. "
                    "Return JSON only with keys: signal (BUY/SELL/WAIT), confidence (0-100), "
                    "validation (true/false), reason (short), risk_flags (array), provider_note (short). "
                    "Use ONLY the deterministic fields and price-action context supplied below. "
                    "Do not invent market data and do not add ICT, FVG, Order Blocks, RSI, MACD or unrelated strategies. "
                    "Hard rules: no valid wick rejection = WAIT; no MTF/storyline agreement = WAIT; no 2-TF confirmation = WAIT; "
                    "false/conflicting breakout = WAIT. AI must confirm the deterministic direction, never override a hard WAIT.\n\n" +
                    json.dumps(ai_context, ensure_ascii=False, default=str)
                )
                text, provider = await ai_json_completion(prompt)
                parsed = json.loads(text)
                sig = str(parsed.get("signal", "WAIT")).upper()
                ai = {
                    "signal": sig if sig in {"BUY", "SELL", "WAIT"} else "WAIT",
                    "confidence": max(0, min(100, int(parsed.get("confidence", 0)))),
                    "validation": bool(parsed.get("validation", False)),
                    "provider": provider,
                    "mode": "live_ai",
                    "reason": str(parsed.get("reason", "AI validation returned no reason.")),
                    "risk_flags": parsed.get("risk_flags") if isinstance(parsed.get("risk_flags"), list) else [],
                    "provider_note": str(parsed.get("provider_note", "")),
                }
            except Exception as exc:
                ai["reason"] = f"AI unavailable: {str(exc)}"
            if ai.get("mode") == "live_ai":
                MSAI_AI_CACHE[ai_key] = (ai_now, candle_time, dict(ai))
            else:
                MSAI_AI_CACHE[ai_key] = (ai_now, candle_time, {**ai, "_failure_cache": True})

    deterministic_ready = bool(base.get("signal") in {"BUY", "SELL"})
    ai_ready = bool(ai.get("validation") and ai.get("signal") == base.get("raw_direction") and int(ai.get("confidence", 0)) >= 65)
    final_signal = base.get("raw_direction") if deterministic_ready and ai_ready else "WAIT"
    if final_signal in {"BUY", "SELL"}:
        base["signal"] = final_signal
        base["state"] = "AI_CONFIRMED"
        base["setup"] = "MSAI_AI_CONFIRMED"
    else:
        base["signal"] = "WAIT"
        if deterministic_ready:
            base["state"] = "WAIT_AI_VALIDATION"
            base["setup"] = "WAIT_AI_VALIDATION"
        if "NO VALIDATION" not in str(base.get("reason", "")):
            base["reason"] = (base.get("reason", "") + "; AI validation not confirmed").strip("; ")
        base["entry"] = None
        base["stop_loss"] = None
        base["take_profit"] = []

    base["ai"] = ai
    base["ai_gate"] = {"required": True, "passed": ai_ready}
    base["strategy_engine"] = "SIGNALX — MSAI STRATEGY v1.0"
    base["strategy_source"] = "Trading SNR the Malaysian Way + AI validation"
    base["session_context"] = (await market_sessions()).get("sessions", [])
    base["lower_timeframe"] = lower_tf
    base["errors"] = errors
    base["generated_at"] = datetime.now(timezone.utc).isoformat()
    result = {
        "ok": True,
        "symbol": key,
        "selected": selected,
        "current_price": round(float(selected_candles[-1]["close"]), 5),
        "candle_time": candle_time,
        "strategy": base,
        "generated_at": base["generated_at"],
    }
    MSAI_CACHE[cache_key] = (now_mono, result)
    return result


@app.get("/api/v1/msai-strategy/{symbol:path}")
async def get_msai_strategy(symbol: str, interval: str = Query("5min")) -> dict[str, Any]:
    selected = validate_interval(interval)
    try:
        return await build_msai_strategy(clean_symbol(symbol), selected)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="MSAI Strategy unavailable: " + str(exc))



async def build_algo_smc_strategy(symbol: str, selected: str, prefetched: dict[str, tuple[list[dict[str, Any]], str, Any]] | None = None) -> dict[str, Any]:
    """Algo/SMC strategy based on the uploaded 232-page Algo/SMC book.

    Deterministic layer follows the source concepts: liquidity hierarchy, daily/weekly/HTF
    cycle, AMD, money transfer, strong/weak highs and lows, premium/discount, fake structure
    breaks, algo candle, FVG/inefficiency and LTF confirmation. AI is a strict validator and
    provider-unavailable means WAIT (no deterministic fallback is allowed for this module).
    """
    key = clean_symbol(symbol)
    cache_key = f"{key}|{selected}"
    now_mono = asyncio.get_running_loop().time()
    cached = ALGO_SMC_CACHE.get(cache_key)
    if prefetched is None and cached and now_mono - cached[0] < ALGO_SMC_CACHE_TTL:
        return cached[1]

    raw = prefetched or {}
    errors: dict[str, str] = {}
    async def get_tf(tf: str, limit: int):
        if tf in raw and raw[tf][0]:
            return raw[tf]
        try:
            return await get_candles(key, tf, limit)
        except Exception as exc:
            errors[tf] = f"{type(exc).__name__}: {exc}"
            return ([], "error", None)

    selected_data, _, _ = await get_tf(selected, 260)
    daily_data, _, _ = await get_tf("1day", 260)
    hourly_data, _, _ = await get_tf("1h", 260)
    h4_data, _, _ = await get_tf("4h", 220)
    m30_data, _, _ = await get_tf("30min", 220)
    m15_data, _, _ = await get_tf("15min", 220)
    m5_data, _, _ = await get_tf("5min", 220)

    def tf_row(name: str, candles: list[dict[str, Any]]) -> dict[str, Any]:
        if len(candles) < 40:
            return {"label": name, "trend": "UNAVAILABLE", "bos": "NONE", "choch": "NONE", "available": False}
        try:
            from algo_smc_strategy import _structure as _algo_structure
            st = _algo_structure(candles)
            return {"label": name, "trend": st.get("trend", "NEUTRAL"), "bos": st.get("bos", "NONE"), "choch": st.get("choch", "NONE"), "available": True}
        except Exception:
            return {"label": name, "trend": "UNAVAILABLE", "bos": "NONE", "choch": "NONE", "available": False}

    rows = [
        tf_row("Daily", daily_data),
        tf_row("H4", h4_data),
        tf_row("H1", hourly_data),
        tf_row("M30", m30_data),
        tf_row("M15", m15_data),
        tf_row("M5", m5_data),
        tf_row(selected.upper(), selected_data) if selected not in {"1day","1h","4h","30min","15min","5min"} else None,
    ]
    rows = [r for r in rows if r]
    bullish = sum(1 for r in rows if r.get("trend") == "BULLISH")
    bearish = sum(1 for r in rows if r.get("trend") == "BEARISH")
    weekly = __import__("algo_smc_strategy")._aggregate(daily_data, "week") if daily_data else []
    weekly_trend = __import__("algo_smc_strategy")._direction_from_swings(weekly) if len(weekly) >= 5 else "NEUTRAL"
    direction_bias = "BULLISH" if weekly_trend == "BULLISH" or bullish > bearish + 1 else "BEARISH" if weekly_trend == "BEARISH" or bearish > bullish + 1 else "NEUTRAL"
    mtf = {"direction_bias": direction_bias, "alignment": direction_bias in {"BULLISH","BEARISH"}, "rows": rows, "bullish_count": bullish, "bearish_count": bearish, "weekly_trend": weekly_trend}

    base = analyze_algo_smc(selected_data, daily_data, hourly_data, mtf, selected)
    if not selected_data:
        base["signal"] = "WAIT"
    candle_time = selected_data[-1].get("time") if selected_data else None

    deterministic_ready = base.get("signal") in {"BUY", "SELL"} and base.get("state") == "READY_FOR_AI"
    ai = {
        "mode": "not_called", "signal": "WAIT", "confidence": 0, "agreement": 0,
        "validation": False, "risk_flags": [],
        "reasoning": "Deterministic setup is not ready for AI validation."
    }
    if deterministic_ready:
        try:
            ai = await ai_validate_module_signal("Algo/SMC", key, selected, candle_time, base)
        except Exception as exc:
            ai = {"mode": "unavailable", "signal": "WAIT", "confidence": 0, "agreement": 0, "validation": False, "risk_flags": ["AI validation exception"], "reasoning": str(exc)[:300]}

    ai_passed = bool(ai.get("validation") and ai.get("signal") == base.get("raw_direction") and int(ai.get("confidence", 0)) >= 85 and int(ai.get("agreement", 0)) >= 70)
    if deterministic_ready and ai_passed:
        base["signal"] = base.get("raw_direction")
        base["state"] = "AI_CONFIRMED"
        base["setup"] = "ALGO_SMC_AI_CONFIRMED"
    else:
        if deterministic_ready:
            base["state"] = "WAIT_AI_VALIDATION"
        base["signal"] = "WAIT"
        base["entry"] = None
        base["stop_loss"] = None
        base["take_profit"] = []
        if "AI validation" not in str(base.get("reason", "")):
            base["reason"] = (base.get("reason", "") + " · AI validation required").strip(" ·")

    base["ai"] = ai
    base["ai_gate"] = {"required": True, "passed": ai_passed, "minimum_confidence": 85, "minimum_agreement": 70, "strict": True}
    base["mtf"] = mtf
    base["errors"] = errors
    base["session_context"] = (await market_sessions()).get("sessions", [])
    base["strategy_engine"] = "SIGNALX — ALGO/SMC + AI"
    base["strategy_version"] = "V1.0"
    base["strategy_source"] = "232-page Algo concept / SMC book + strict AI validation"
    base["candle_time"] = candle_time
    base["generated_at"] = datetime.now(timezone.utc).isoformat()
    result = {"ok": True, "symbol": key, "selected": selected, "current_price": base.get("current_price"), "candle_time": candle_time, "strategy": base, "generated_at": base["generated_at"]}
    if prefetched is None:
        ALGO_SMC_CACHE[cache_key] = (now_mono, result)
    return result


@app.get("/api/v1/algo-smc/{symbol:path}")
async def get_algo_smc(symbol: str, interval: str = Query("5min")) -> dict[str, Any]:
    selected = validate_interval(interval)
    try:
        return await build_algo_smc_strategy(clean_symbol(symbol), selected)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Algo/SMC unavailable: " + str(exc))


async def build_smc_strategy(symbol: str, selected: str) -> dict[str, Any]:
    """SIGNALX SMC strategy derived from the uploaded 33-page SMC manual.

    Deterministic layer: structure (BOS/CHoCH), liquidity (EQH/EQL/sweeps),
    POI (Order Block/FVG), IDM, MTF context and LTF entry modules. AI only validates.
    """
    cache_key = f"{clean_symbol(symbol)}|{selected}"
    now_mono = asyncio.get_running_loop().time()
    cached = SMC_CACHE.get(cache_key)
    if cached and now_mono - cached[0] < SMC_CACHE_TTL:
        return cached[1]

    key = clean_symbol(symbol)
    tf_list = ["1min", "5min", "15min", "30min", "1h", "4h", "1day"]
    raw: dict[str, tuple[list[dict[str, Any]], str, Any]] = {}
    errors: dict[str, str] = {}
    for tf in tf_list:
        try:
            raw[tf] = await get_candles(key, tf, 220 if tf in {"1min", "5min"} else 180)
        except Exception as exc:
            errors[tf] = f"{type(exc).__name__}: {exc}"

    selected_candles = raw.get(selected, ([], "error", None))[0]
    if len(selected_candles) < 60:
        raise MarketDataError(f"SMC uchun {selected} timeframe candle yetarli emas")

    mtf_rows: dict[str, dict[str, Any]] = {}
    for tf, pack in raw.items():
        candles = pack[0]
        if len(candles) >= 60:
            local = analyze_smc(candles, {"direction_bias": "NEUTRAL", "alignment": False}, tf)
            mtf_rows[tf] = {
                "trend": local.get("structure", {}).get("trend", "NEUTRAL"),
                "bos": local.get("structure", {}).get("bos"),
                "choch": local.get("structure", {}).get("choch"),
                "price": round(float(candles[-1]["close"]), 5),
            }
    daily = raw.get("1day", ([], "error", None))[0]
    weekly = aggregate_weekly(daily)
    if weekly and len(weekly) >= 8:
        mtf_rows["1week"] = {"trend": direction_from_candles(weekly), "price": round(float(weekly[-1]["close"]), 5)}

    smc_mtf = summarize_smc_mtf(mtf_rows)
    direction_bias = smc_mtf.get("direction_bias", "NEUTRAL")
    base = analyze_smc(selected_candles, {"direction_bias": direction_bias, "alignment": bool(smc_mtf.get("alignment"))}, selected)
    base["mtf"] = smc_mtf
    base["mtf_timeframes"] = mtf_rows
    base["errors"] = errors

    # Manual examples use HTF→LTF refinement such as M15→M1 and H1→M5.
    lower_map = {"1day":"1h", "4h":"15min", "1h":"5min", "30min":"5min", "15min":"1min", "5min":"1min", "1min":"1min"}
    lower_tf = lower_map.get(selected, "1min")
    lower_candles = raw.get(lower_tf, ([], "error", None))[0]
    ltf = {"timeframe": lower_tf, "signal": "WAIT", "valid": False, "modules": {}, "structure": {}}
    raw_direction = base.get("raw_direction", "WAIT")
    if len(lower_candles) >= 60 and raw_direction in {"BUY", "SELL"}:
        lower = analyze_smc(lower_candles, {"direction_bias": "BULLISH" if raw_direction == "BUY" else "BEARISH", "alignment": True}, lower_tf)
        ltf = {
            "timeframe": lower_tf,
            "signal": lower.get("signal", "WAIT"),
            "valid": bool(lower.get("raw_direction") == raw_direction and (lower.get("checks", {}).get("structure_bos_choch") or lower.get("checks", {}).get("entry_module"))),
            "modules": lower.get("entry_modules", {}),
            "structure": lower.get("structure", {}),
            "score": lower.get("score", 0),
        }
    base["ltf_confirmation"] = ltf

    checks = dict(base.get("checks") or {})
    checks["ltf_confirmation"] = bool(ltf.get("valid"))
    checks["mtf_alignment"] = bool(smc_mtf.get("alignment")) and raw_direction == direction_bias
    base["checks"] = checks

    candle_time = selected_candles[-1].get("time")
    ai_key = f"{key}|{selected}"
    async with SMC_AI_LOCKS_GUARD:
        ai_lock = SMC_AI_LOCKS.setdefault(ai_key, asyncio.Lock())
    async with ai_lock:
        ai_now = datetime.now(timezone.utc).timestamp()
        cached_ai = SMC_AI_CACHE.get(ai_key)
        ai = None
        if cached_ai and cached_ai[1] == candle_time:
            cached_payload = dict(cached_ai[2])
            cached_ttl = AI_FAILURE_CACHE_TTL if cached_payload.get("_failure_cache") else AI_CACHE_TTL
            if ai_now - cached_ai[0] < cached_ttl:
                cached_payload.pop("_failure_cache", None)
                ai = cached_payload
        if ai is None:
            ai = {"signal":"WAIT", "confidence":0, "validation":False,
                  "provider":None, "mode":"unavailable", "reason":"AI network unavailable; no signal emitted.", "risk_flags":[]}
            ai_context = {
                "symbol": key,
                "timeframe": selected,
                "current_price": selected_candles[-1].get("close"),
                "deterministic_signal": raw_direction,
                "deterministic_score": base.get("score", 0),
                "state": base.get("state"),
                "checks": checks,
                "structure": base.get("structure", {}),
                "liquidity": base.get("liquidity", {}),
                "order_block": base.get("order_block", {}),
                "fvg": base.get("fvg", {}),
                "idm": base.get("idm", {}),
                "entry_modules": base.get("entry_modules", {}),
                "ltf_confirmation": ltf,
                "mtf": smc_mtf,
                "rule": "Use only the supplied Smart Money Concepts manual. Validate, do not invent. Focus on BOS/CHoCH, liquidity, IDM, OB, FVG, POI, MTF and LTF entry modules. Return WAIT when validation is incomplete or direction conflicts.",
            }
            try:
                prompt = (
                    "You are the AI validation layer for SIGNALX — SMC. The strategy is derived from the supplied Smart Money Concepts manual. "
                    "Return JSON only with keys: signal (BUY/SELL/WAIT), confidence (0-100), validation (true/false), reason (short), risk_flags (array), provider_note (short). "
                    "Use ONLY supplied deterministic data. Never invent price levels. Hard rules: no structure/entry module = WAIT; no MTF agreement = WAIT; no LTF confirmation = WAIT; RR below implementation minimum = WAIT; conflicting direction = WAIT. "
                    "AI confirms/rejects and never overrides a hard WAIT.\n\n" + json.dumps(ai_context, ensure_ascii=False, default=str)
                )
                text, provider = await ai_json_completion(prompt)
                parsed = json.loads(text)
                sig = str(parsed.get("signal", "WAIT")).upper()
                ai = {
                    "signal": sig if sig in {"BUY","SELL","WAIT"} else "WAIT",
                    "confidence": max(0, min(100, int(parsed.get("confidence", 0)))),
                    "validation": bool(parsed.get("validation", False)),
                    "provider": provider,
                    "mode": "live_ai",
                    "reason": str(parsed.get("reason", "AI validation returned no reason.")),
                    "risk_flags": parsed.get("risk_flags") if isinstance(parsed.get("risk_flags"), list) else [],
                    "provider_note": str(parsed.get("provider_note", "")),
                }
            except Exception as exc:
                ai["reason"] = f"AI unavailable: {str(exc)}"
            if ai.get("mode") == "live_ai":
                SMC_AI_CACHE[ai_key] = (ai_now, candle_time, dict(ai))
            else:
                SMC_AI_CACHE[ai_key] = (ai_now, candle_time, {**ai, "_failure_cache": True})

    deterministic_ready = bool(raw_direction in {"BUY","SELL"} and checks.get("structure_bos_choch") and checks.get("entry_module") and checks.get("ltf_confirmation") and checks.get("mtf_alignment") and checks.get("rr_ok"))
    ai_gate = bool(deterministic_ready and ai.get("validation") and ai.get("signal") == raw_direction and int(ai.get("confidence", 0)) >= 75)
    base["signal"] = raw_direction if ai_gate else "WAIT"
    base["ai"] = ai
    base["ai_gate"] = {"passed": ai_gate, "threshold": 75}
    if ai_gate:
        base["state"] = "AI_CONFIRMED"
        base["setup"] = "SMC_AI_CONFIRMED"
        base["reason"] = (base.get("reason", "") + "; AI confirmed").strip("; ")
    else:
        base["state"] = "WAIT_AI_VALIDATION" if raw_direction in {"BUY","SELL"} else base.get("state", "WAIT")
        base["setup"] = "WAIT_AI_VALIDATION"
        base["entry"] = None
        base["stop_loss"] = None
        base["take_profit"] = []
        base["reason"] = (base.get("reason", "") + "; NO VALIDATION, NO TRADE").strip("; ")

    base["strategy_engine"] = "SIGNALX — SMC"
    base["strategy_source"] = "Smart Money Concepts manual + AI validation"
    base["source_scope"] = ["BOS/CHoCH", "Liquidity", "IDM", "Order Block", "FVG", "POI", "Session Liquidity", "MTF", "LTF Entry Modules", "Risk Management"]
    base["lower_timeframe"] = lower_tf
    base["current_price"] = round(float(selected_candles[-1]["close"]), 5)
    base["candle_time"] = candle_time
    base["generated_at"] = datetime.now(timezone.utc).isoformat()
    SMC_CACHE[cache_key] = (now_mono, base)
    return base


@app.get("/api/v1/smc/{symbol:path}")
async def get_smc(symbol: str, interval: str = Query("5min")) -> dict[str, Any]:
    selected = validate_interval(interval)
    try:
        return await build_smc_strategy(clean_symbol(symbol), selected)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="SMC unavailable: " + str(exc))

@app.get("/api/v1/classic-trade/{symbol:path}")
async def get_classic_trade(symbol: str, interval: str = Query(DEFAULT_INTERVAL)) -> dict[str, Any]:
    symbol = clean_symbol(symbol); interval = validate_interval(interval)
    try:
        candles, mode, warning = await get_candles(symbol, interval, 220)
        if len(candles) < 60: raise MarketDataError("Classic Trade uchun candle yetarli emas")
        ref = candles[-2]; price = float(candles[-1]["close"])
        levels = calculate_pivot_levels(float(ref["high"]), float(ref["low"]), float(ref["close"]), price)
        classic = _classic_trade(candles, levels)
        ai_advisory = await _module_ai_advisory("Classic Trade", symbol, interval, ref.get("time"), classic)
        classic["ai_validation"] = ai_advisory
        return {"ok":True,"symbol":symbol,"interval":interval,"mode":mode,"warning":warning,"current_price":round(price,4),"candle_time":ref.get("time"),"classic":classic,"generated_at":datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Classic Trade unavailable: "+str(exc))

@app.get("/api/v1/ai-smart-analysis/{symbol:path}")
async def get_ai_smart_analysis(symbol: str, interval: str = Query(DEFAULT_INTERVAL), authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    require_admin(authorization, session)
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
        candles_data, _, _ = await get_candles(symbol, interval, 220)
        if len(candles_data) < 35:
            raise MarketDataError("TradingView candles yetarli emas")
        levels, _ = await calculate_pivot_for_interval(symbol, interval)
        setup = build_key_level_signal(candles_data, levels, news_blocked=False)
        technical = technical_analysis(candles_data, levels, setup)
        candle_time=candles_data[-2].get("time") if len(candles_data)>1 else candles_data[-1].get("time")
        technical["ai_validation"] = await _module_ai_advisory("Technical Analysis", symbol, interval, candle_time, technical)
        fib_context = analyze_fibonacci(candles_data, {interval: candles_data})
        technical["fibonacci"] = fib_context
        return {
            "ok": True, "symbol": symbol, "interval": interval, "mode": "tradingview",
            "provider": "TradingView", "source": tv_symbol_for(symbol),
            "current_price": round(float(candles_data[-1]["close"]), 4),
            "candles": candles_data, "candle_time": candles_data[-2].get("time") if len(candles_data)>1 else candles_data[-1].get("time"), "levels": levels, "technical": technical, "fibonacci": technical.get("fibonacci"),
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



async def refresh_signal_outcomes(session: Session, user_id: int, limit: int = 500) -> list[SignalHistory]:
    """Resolve live History outcomes from post-signal candles and the latest quote.

    The original signal snapshot is never changed. Only lifecycle fields are updated:
    ACTIVE -> TP1 HIT -> TP2 HIT / SL HIT. A TP2/SL final result is terminal and is
    never treated as a new signal.
    """
    rows = list(session.scalars(select(SignalHistory).where(
        SignalHistory.user_id == user_id,
        ~SignalHistory.source.in_(LEGACY_EXCLUDED_SIGNAL_SOURCES)
    ).order_by(SignalHistory.created_at.desc(), SignalHistory.id.desc()).limit(limit)).all())

    def parse_dt(value: Any) -> datetime | None:
        if value is None or value == "":
            return None
        try:
            if isinstance(value, (int, float)):
                return datetime.fromtimestamp(float(value), tz=timezone.utc)
            raw = str(value).strip()
            if raw.isdigit():
                return datetime.fromtimestamp(float(raw), tz=timezone.utc)
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return None

    cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
    changed = False

    for row in rows:
        try:
            try:
                payload = json.loads(row.payload or "{}")
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                payload = {"raw_payload": payload}

            _history_sync_row(row, payload)
            entry, sl, tp1, tp2 = row.entry_price, row.stop_loss, row.take_profit_1, row.take_profit_2
            if entry is None or sl is None or tp1 is None or row.direction not in {"BUY", "SELL"}:
                continue
            if tp2 is None:
                tp2 = tp1

            # A signal with TP/SL on the wrong side of entry is malformed and must
            # never be classified as a profitable hit. Keep the journal honest.
            valid_geometry = (
                row.direction == "BUY" and float(sl) < float(entry) and float(tp1) > float(entry) and float(tp2) > float(entry)
            ) or (
                row.direction == "SELL" and float(sl) > float(entry) and float(tp1) < float(entry) and float(tp2) < float(entry)
            )
            if not valid_geometry:
                row.status = "CANCELLED"
                row.outcome = "CANCELLED"
                row.result = "CANCELLED"
                row.closed_at = row.closed_at or datetime.now(timezone.utc)
                payload["result"] = {
                    "status": "CANCELLED",
                    "price": None,
                    "reason": "INVALID_LEVEL_GEOMETRY",
                    "message": "Entry/SL/TP levels are inconsistent with signal direction."
                }
                row.payload = json.dumps(payload, ensure_ascii=False)
                row.profit_loss = None
                row.r_multiple = None
                changed = True
                continue

            # Terminal valid rows must never be re-resolved.
            if str(row.status or "").upper() in {"TP2 HIT", "SL HIT", "CANCELLED", "EXPIRED"} or str(row.outcome or "").upper() in {"TP2 HIT", "TP HIT", "SL HIT", "CANCELLED", "EXPIRED"}:
                continue

            try:
                normalized_interval = validate_interval(row.interval)
            except Exception:
                continue
            key = (clean_symbol(row.symbol), normalized_interval)
            if key not in cache:
                try:
                    raw_candles = await get_candles(row.symbol, normalized_interval, 260)
                    if isinstance(raw_candles, tuple):
                        raw_candles = raw_candles[0] if raw_candles else []
                    cache[key] = raw_candles if isinstance(raw_candles, list) else []
                except Exception:
                    cache[key] = []

            candles = [c for c in cache[key] if isinstance(c, dict)]
            if not candles:
                continue

            created = row.created_at
            if created is None:
                continue
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            else:
                created = created.astimezone(timezone.utc)
            signal_bar = parse_dt(row.candle_time) or created

            tp1_hit = None
            tp1_time = None
            final = None
            final_price = None
            final_time = None

            # Historical candles after the signal candle. Using candle_time rather
            # than created_at is important when the signal was created mid-candle.
            ordered = sorted(candles, key=lambda c: parse_dt(c.get("time")) or datetime.min.replace(tzinfo=timezone.utc))
            for c in ordered:
                cdt = parse_dt(c.get("time"))
                if cdt is None or cdt < signal_bar:
                    continue
                # On the candle that generated the signal, do not infer an outcome
                # from price movement that happened before the signal timestamp.
                if cdt == signal_bar and cdt <= created:
                    continue
                try:
                    high = float(c.get("high")); low = float(c.get("low")); close = float(c.get("close"))
                except (TypeError, ValueError):
                    continue

                if row.direction == "BUY":
                    hit1 = high >= float(tp1)
                    hit2 = high >= float(tp2)
                    hit_sl = low <= float(sl)
                else:
                    hit1 = low <= float(tp1)
                    hit2 = low <= float(tp2)
                    hit_sl = high >= float(sl)

                if tp1_hit is None and hit1:
                    tp1_hit = float(tp1)
                    tp1_time = cdt

                if hit2 and hit_sl:
                    final = "CANCELLED"
                    final_price = close
                    final_time = cdt
                    break
                if hit2:
                    final = "TP2 HIT"
                    final_price = float(tp2)
                    final_time = cdt
                    break
                if hit_sl:
                    final = "SL HIT"
                    final_price = float(sl)
                    final_time = cdt
                    break

            # Also evaluate the latest live close/quote so a signal can be resolved
            # during the currently-open candle rather than waiting for the next bar.
            if final is None:
                try:
                    latest = candles[-1]
                    latest_dt = parse_dt(latest.get("time"))
                    current_price = float(latest.get("close"))
                    if latest_dt and latest_dt >= signal_bar and latest_dt > created:
                        if row.direction == "BUY":
                            if current_price >= float(tp2):
                                final, final_price, final_time = "TP2 HIT", float(tp2), datetime.now(timezone.utc)
                            elif current_price <= float(sl):
                                final, final_price, final_time = "SL HIT", float(sl), datetime.now(timezone.utc)
                            elif current_price >= float(tp1) and tp1_hit is None:
                                tp1_hit, tp1_time = float(tp1), datetime.now(timezone.utc)
                        else:
                            if current_price <= float(tp2):
                                final, final_price, final_time = "TP2 HIT", float(tp2), datetime.now(timezone.utc)
                            elif current_price >= float(sl):
                                final, final_price, final_time = "SL HIT", float(sl), datetime.now(timezone.utc)
                            elif current_price <= float(tp1) and tp1_hit is None:
                                tp1_hit, tp1_time = float(tp1), datetime.now(timezone.utc)
                except Exception:
                    pass

            timeline = payload.get("timeline") if isinstance(payload.get("timeline"), dict) else {}
            if tp1_hit is not None and tp1_time is not None and not timeline.get("tp1_hit"):
                timeline["tp1_hit"] = tp1_time.isoformat()

            if final and final_time:
                row.status = final
                row.result = final
                row.closed_at = final_time
                pnl, rm = _history_result_metrics(row, final, final_price)
                row.profit_loss = pnl
                row.r_multiple = rm
                timeline["final"] = final_time.isoformat()
                payload["timeline"] = timeline
                payload["result"] = {
                    "status": final,
                    "price": round(float(final_price), 4) if final_price is not None else None,
                    "candle_time": final_time.isoformat(),
                    "duration_seconds": max(0, int((final_time - created).total_seconds())),
                    "profit_loss": pnl,
                    "r_multiple": rm,
                }
                row.payload = json.dumps(payload, ensure_ascii=False)
                row.outcome = final
                changed = True
            elif tp1_hit is not None and _history_status(row) == "ACTIVE":
                row.status = "TP1 HIT"
                row.outcome = "TP1 HIT"
                payload["timeline"] = timeline
                row.payload = json.dumps(payload, ensure_ascii=False)
                changed = True
        except Exception as exc:
            # One broken legacy row must never abort the remaining journal.
            print(f"[HISTORY OUTCOME] skip id={getattr(row,'id',None)} error={type(exc).__name__}: {exc}")
            continue

    if changed:
        try:
            session.commit()
        except Exception as exc:
            session.rollback()
            print(f"[HISTORY OUTCOME] commit_warning={type(exc).__name__}: {exc}")

    return list(session.scalars(
        select(SignalHistory).where(SignalHistory.user_id == user_id)
        .order_by(SignalHistory.created_at.desc(), SignalHistory.id.desc()).limit(limit)
    ).all())


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
        result["ai_validation"] = await _module_ai_advisory("ICT Signals", symbol, "30min", candle_time, result)
        result["candle_time"]=candle_time
        return {"ok":True,"symbol":symbol,"mode":"live","source":"TradingView/OANDA canonical candle series",
                "m30_candles":len(c30),"m5_candles":len(c5),"warnings":[x for x in (w30,w5) if x],
                "ict":result,"generated_at":datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        return {"ok":False,"symbol":symbol,"mode":"error","error":str(exc),
                "ict":{"signal":"WAIT","confidence":0,"score":0,"reason":str(exc)}}




async def build_fibonacci_strategy(symbol: str, selected: str = "5min") -> dict[str, Any]:
    """Eight-book Fibonacci/Fibo Musang strategy + strict AI validation."""
    key = clean_symbol(symbol)
    selected = validate_interval(selected)
    raw: dict[str, tuple[list[dict[str, Any]], str, Any]] = {}
    errors: dict[str, str] = {}

    async def load(tf: str, limit: int = 280):
        try:
            raw[tf] = await get_candles(key, tf, limit)
        except Exception as exc:
            raw[tf] = ([], "error", None)
            errors[tf] = f"{type(exc).__name__}: {exc}"

    await asyncio.gather(*(load(tf) for tf in {selected, "1day", "4h", "1h"}))
    selected_data = raw.get(selected, ([], "error", None))[0]
    higher = {tf: raw.get(tf, ([], "error", None))[0] for tf in ("1day", "4h", "1h")}
    if len(selected_data) < 60:
        return {"ok": False, "symbol": key, "selected": selected, "error": "Fibonacci uchun real candle yetarli emas.",
                "generated_at": datetime.now(timezone.utc).isoformat()}

    deterministic = analyze_fibonacci(selected_data, higher)
    candle_time = selected_data[-2].get("time") if len(selected_data) > 1 else selected_data[-1].get("time")
    ai = await ai_validate_module_signal("Fibonacci", key, selected, candle_time, deterministic)
    live_ai = str(ai.get("mode") or "") not in {"fallback", "rule_based", "unavailable"}
    ai_passed = bool(live_ai and ai.get("validation") and
                     str(ai.get("signal")).upper() == str(deterministic.get("signal")).upper() and
                     int(ai.get("confidence", 0)) >= 85 and int(ai.get("agreement", 0)) >= 70)

    final = dict(deterministic)
    final["ai_validation"] = ai
    final["ai_gate"] = {"required": True, "passed": ai_passed, "minimum_confidence": 85,
                         "minimum_agreement": 70, "live_ai_required": True}
    if final.get("signal") in {"BUY", "SELL"} and not ai_passed:
        final["signal"] = "WAIT"
        final["entry"] = None
        final["stop_loss"] = None
        final["take_profit"] = []
        final["state"] = "WAIT_AI_VALIDATION"
        final["reason"] = (str(final.get("reason") or "") + "; AI validation required").strip("; ")
    else:
        final["state"] = "AI_CONFIRMED" if final.get("signal") in {"BUY", "SELL"} else final.get("state", "WAIT")
    final["strategy_engine"] = "SIGNALX — FIBONACCI"
    final["strategy_version"] = "V1.0"
    final["strategy_source"] = "8 Fibonacci/Fibo Musang books + deterministic confluence + strict AI validation"
    final["book_coverage"] = [
        "25 — Fibo Musang Final BOBI / Home Course",
        "26 — Fibo Musang Elite: Fibo Setting & Cara Kerja Fibo",
        "27 — Fibonacci for the Active Trader",
        "28 — The Advanced Guide to Fibonacci Trading",
        "29 — Fibonacci Trading: How to Master the Time and Price Advantage",
        "30 — Fibonachchi Darajalari 2-qism",
        "31 — Rahsia Fibo Musang 2011–2015",
        "32 — The Most Powerful Setup of Fibo Musang / 6 Setups",
    ]
    final["book_routing"] = [
        {"books": "25,26,31,32", "module": "Fibonacci / Patterns", "focus": "Fibo Musang, CBR, Initial Break, Dominant Candle, nearest S/R break, 261/423 cycle, reversal patterns"},
        {"books": "27,28,30", "module": "Fibonacci / Technical Analysis", "focus": "retracement, extension, projection, 50% + Pin Bar, volatility filter, false-signal filter"},
        {"books": "29", "module": "Fibonacci / MTF", "focus": "price clusters, symmetry, two-step pattern, time-price confluence, active swing selection"},
        {"books": "27-32", "module": "Trend Line / Trend Channel", "focus": "Fibo + trendline, Fibo + S/R, Fibo cluster + channel boundary confluence"},
        {"books": "27-32", "module": "Risk Engine", "focus": "swing-based invalidation, extension targets, RR gate, no-trade on extreme volatility / weak context"},
        {"books": "25-32", "module": "AI Validation", "focus": "pattern does not invent signal; AI validates deterministic evidence"},
    ]
    final["current_price"] = round(float(selected_data[-1]["close"]), 5)
    final["candle_time"] = candle_time
    final["errors"] = errors
    final["generated_at"] = datetime.now(timezone.utc).isoformat()
    return {"ok": True, "symbol": key, "selected": selected, "strategy": final, "generated_at": final["generated_at"]}


async def build_trend_channel_strategy(symbol: str, selected: str = "5min") -> dict[str, Any]:
    """Six-book Trend Channel Engine + strict AI validator."""
    key = clean_symbol(symbol)
    selected = validate_interval(selected)
    raw: dict[str, tuple[list[dict[str, Any]], str, Any]] = {}
    errors: dict[str, str] = {}
    async def load(tf: str, limit: int = 260):
        try:
            raw[tf] = await get_candles(key, tf, limit)
        except Exception as exc:
            errors[tf] = f"{type(exc).__name__}: {exc}"
            raw[tf] = ([], "error", None)
    await asyncio.gather(*(load(tf, 280 if tf in {"1day","4h"} else 260) for tf in {selected, "1h", "4h", "1day"}))
    selected_data = raw.get(selected, ([],"error",None))[0]
    higher = {tf: raw.get(tf,([],"error",None))[0] for tf in ("1day","4h","1h")}
    deterministic = analyze_trend_channel(selected_data, higher)
    fibonacci_context = analyze_fibonacci(selected_data, higher)
    deterministic["fibonacci_context"] = {
        "signal": fibonacci_context.get("signal", "WAIT"),
        "score": fibonacci_context.get("score", 0),
        "nearest_fibonacci": fibonacci_context.get("nearest_fibonacci"),
        "fib_cluster": fibonacci_context.get("fib_cluster"),
        "musang": fibonacci_context.get("musang"),
        "reason": fibonacci_context.get("reason", ""),
    }
    candle_time = selected_data[-2].get("time") if len(selected_data) > 1 else (selected_data[-1].get("time") if selected_data else None)
    ai = await ai_validate_module_signal("Trend Channel Engine", key, selected, candle_time, deterministic)
    live_ai = str(ai.get("mode") or "") not in {"fallback", "rule_based", "unavailable"}
    ai_passed = bool(live_ai and ai.get("validation") and str(ai.get("signal")).upper() == str(deterministic.get("signal")).upper()
                     and int(ai.get("confidence",0)) >= 85 and int(ai.get("agreement",0)) >= 70)
    deterministic["ai_validation"] = ai
    deterministic["ai_gate"] = {"required": True, "passed": ai_passed, "minimum_confidence": 85, "minimum_agreement": 70, "live_ai_required": True}
    if deterministic.get("signal") in {"BUY","SELL"} and not ai_passed:
        deterministic["signal"] = "WAIT"
        deterministic["entry"] = None; deterministic["stop_loss"] = None; deterministic["take_profit"] = []
        deterministic["state"] = "WAIT_AI_VALIDATION"
        deterministic["reason"] = (str(deterministic.get("reason") or "") + "; AI validation required").strip("; ")
    deterministic["strategy_engine"] = "SIGNALX — TREND CHANNEL ENGINE"
    deterministic["strategy_version"] = "V1.0"
    deterministic["strategy_source"] = "Six supplied trend/channel/PSAR books + strict AI validation"
    deterministic["errors"] = errors
    deterministic["current_price"] = round(float(selected_data[-1]["close"]),5) if selected_data else None
    deterministic["candle_time"] = candle_time
    return {"ok": True, "symbol": key, "selected": selected, "strategy": deterministic,
            "generated_at": datetime.now(timezone.utc).isoformat()}


async def build_book_fusion_strategy(symbol: str, selected: str = "5min",
                                    prefetched: dict[str, tuple[list[dict[str, Any]], str, Any]] | None = None) -> dict[str, Any]:
    """Independent all-book fusion: deterministic multi-engine consensus + one AI validator.

    When the live signal pipeline already has canonical candles, they can be supplied via
    ``prefetched`` so the fusion engine uses exactly the same chart series without issuing
    another batch of market-data requests.
    """
    key = clean_symbol(symbol); selected = validate_interval(selected)
    order = list(dict.fromkeys([selected, "1day", "4h", "1h", "30min", "15min", "5min"]))
    raw: dict[str, tuple[list[dict[str, Any]], str, Any]] = dict(prefetched or {})
    errors: dict[str,str] = {}
    missing=[tf for tf in order if tf not in raw]
    async def load(tf: str):
        try: raw[tf] = await get_candles(key, tf, 280)
        except Exception as exc:
            raw[tf] = ([],"error",None); errors[tf] = f"{type(exc).__name__}: {exc}"
    if missing:
        await asyncio.gather(*(load(tf) for tf in missing))
    selected_data = raw.get(selected,([],"error",None))[0]
    daily = raw.get("1day",([],"error",None))[0]
    h4 = raw.get("4h",([],"error",None))[0]
    h1 = raw.get("1h",([],"error",None))[0]
    m30 = raw.get("30min",([],"error",None))[0]
    m5 = raw.get("5min",([],"error",None))[0]
    if len(selected_data) < 60:
        return {"ok":False,"symbol":key,"selected":selected,"error":"Yangi Strategiya uchun real candle yetarli emas.","generated_at":datetime.now(timezone.utc).isoformat()}

    weekly = aggregate_weekly(daily)
    weekly_bias = direction_from_candles(weekly) if len(weekly) >= 5 else "NEUTRAL"
    htf_rows=[]
    for tf,c in (("1day",daily),("4h",h4),("1h",h1),("30min",m30),("5min",m5)):
        if len(c)>=30: htf_rows.append({"timeframe":tf,"trend":direction_from_candles(c),"price":round(float(c[-1]["close"]),5)})
    bulls=sum(1 for r in htf_rows if r["trend"]=="BULLISH"); bears=sum(1 for r in htf_rows if r["trend"]=="BEARISH")
    htf_direction = "BULLISH" if bulls>bears else "BEARISH" if bears>bulls else weekly_bias if weekly_bias in {"BULLISH","BEARISH"} else "NEUTRAL"
    mtf={"direction_bias":htf_direction,"alignment":htf_direction in {"BULLISH","BEARISH"},"rows":htf_rows,"bullish_count":bulls,"bearish_count":bears,"weekly_trend":weekly_bias}

    msai_det = analyze_msai(selected_data, {"direction_bias":htf_direction,"alignment":htf_direction==("BULLISH" if direction_from_candles(selected_data)=="BULLISH" else "BEARISH") if direction_from_candles(selected_data) in {"BULLISH","BEARISH"} else False}, selected)
    smc_det = analyze_smc(selected_data, mtf, selected)
    algo_det = analyze_algo_smc(selected_data, daily, h1, mtf, selected)
    channel_det = analyze_trend_channel(selected_data, {"1day":daily,"4h":h4,"1h":h1})
    ict_det = build_ict_m30_m5(m30 if len(m30)>=40 else selected_data, m5 if len(m5)>=40 else selected_data)

    fib_det = analyze_fibonacci(selected_data, {"1day":daily, "4h":h4, "1h":h1})
    components = {
        "ICT Core": ict_det,
        "Algo/SMC": algo_det,
        "SMC": smc_det,
        "MSAI/SNR": msai_det,
        "Trend Channel": channel_det,
        "Fibonacci": fib_det,
    }
    weights={"ICT Core":22,"Algo/SMC":18,"SMC":14,"MSAI/SNR":13,"Trend Channel":13,"Fibonacci":20}
    vote_buy=0.0; vote_sell=0.0
    rows=[]
    for name,item in components.items():
        sig=str(item.get("signal") or item.get("raw_direction") or "WAIT").upper()
        conf=float(item.get("confidence") or item.get("score") or 0)
        weighted=round(weights[name]*(max(0,min(100,conf))/100),2)
        if sig=="BUY": vote_buy += weighted
        elif sig=="SELL": vote_sell += weighted
        rows.append({"engine":name,"signal":sig,"confidence":round(conf,1),"weight":weights[name],"weighted_vote":weighted,
                     "rr":round(float(item.get("risk_reward") or 0),2),"state":item.get("state")})
    direction = "BUY" if vote_buy>vote_sell and vote_buy-vote_sell>=8 else "SELL" if vote_sell>vote_buy and vote_sell-vote_buy>=8 else "WAIT"
    candidates=[(name,item) for name,item in components.items() if str(item.get("signal") or item.get("raw_direction") or "WAIT").upper()==direction]
    best_name,best = max(candidates,key=lambda z:(float(z[1].get("risk_reward") or 0),float(z[1].get("confidence") or z[1].get("score") or 0)),default=(None,{}))

    price=float(selected_data[-1]["close"])
    if daily:
        day20=daily[-20:]; day40=daily[-40:]; day60=daily[-60:]
        liquidity={
            "previous_daily_high": round(float(daily[-2]["high"]),5) if len(daily)>1 else None,
            "previous_daily_low": round(float(daily[-2]["low"]),5) if len(daily)>1 else None,
            "20d_high": round(max(float(c["high"]) for c in day20),5), "20d_low": round(min(float(c["low"]) for c in day20),5),
            "40d_high": round(max(float(c["high"]) for c in day40),5), "40d_low": round(min(float(c["low"]) for c in day40),5),
            "60d_high": round(max(float(c["high"]) for c in day60),5), "60d_low": round(min(float(c["low"]) for c in day60),5),
            "daily_open": round(float(daily[-1]["open"]),5),
        }
        q_hi=max(float(c["high"]) for c in daily[-63:]) if len(daily)>=10 else price
        q_lo=min(float(c["low"]) for c in daily[-63:]) if len(daily)>=10 else price
        eq=(q_hi+q_lo)/2
        pd="PREMIUM" if price>eq else "DISCOUNT" if price<eq else "EQUILIBRIUM"
        macro={"quarter_context": "BULLISH" if price>eq and price>float(daily[-min(30,len(daily))]["close"]) else "BEARISH" if price<eq else "NEUTRAL",
               "premium_discount":pd,"equilibrium":round(eq,5),"lookback":liquidity,
               "external_feeds":{"COT":"NOT_CONNECTED","USDX":"NOT_CONNECTED","OPEN_INTEREST":"NOT_CONNECTED","INTEREST_RATES":"NOT_CONNECTED","SEASONALITY":"NOT_CONNECTED"}}
    else:
        macro={"quarter_context":"UNAVAILABLE","premium_discount":"UNAVAILABLE","lookback":{},"external_feeds":{}}

    candidate_rr=float(best.get("risk_reward") or 0) if best_name else 0.0
    mtf_match = direction in {"BUY","SELL"} and (htf_direction==("BULLISH" if direction=="BUY" else "BEARISH") or htf_direction=="NEUTRAL")
    hard_checks={"consensus_direction":direction!="WAIT","mtf_alignment":mtf_match,"rr_ge_1_50":candidate_rr>=1.50,"best_engine":best_name or "NONE",
                 "no_conflicting_majority":abs(vote_buy-vote_sell)>=8,"macro_context_available":bool(daily)}
    deterministic_conf = int(round(min(100,max(vote_buy,vote_sell)))) if direction!="WAIT" else int(round(max(vote_buy,vote_sell)))
    deterministic={"signal":direction if all([hard_checks["consensus_direction"],hard_checks["mtf_alignment"],hard_checks["rr_ge_1_50"]]) else "WAIT",
                   "raw_direction":direction,"confidence":deterministic_conf,"score":deterministic_conf,"reason":" · ".join([f"{r['engine']}={r['signal']} {r['confidence']:.0f}%" for r in rows]),
                   "components":rows,"vote_buy":round(vote_buy,2),"vote_sell":round(vote_sell,2),"mtf":mtf,"macro_context":macro,
                   "selected_engine":best_name,"entry":best.get("entry") if best_name else None,"stop_loss":best.get("stop_loss") if best_name else None,
                   "take_profit":best.get("take_profit",[]) if best_name else [],"risk_reward":candidate_rr,"hard_checks":hard_checks,
                   "book_coverage":[
                       "01 — Trading SNR the Malaysian Way", "02 — SMC Trading Book", "03 — Algo/SMC 232-page Book",
                       "04 — Advanced ICT Institutional SMC Trading Book", "05 — ICT Killzones", "06 — ICT Trading Strategy",
                       "07 — ICT Mentorship Core Content 2016", "08 — September 2016 ICT Study Notes", "09 — October 2016 ICT Study Notes",
                       "10 — November 2016 ICT Study Notes", "11 — December 2016 ICT Study Notes", "12 — January 2017 Long Term Analysis",
                       "13 — February 2017 Swing Trading", "14 — April 2017 ICT Daytrading Model", "15 — June 2017 ICT Community Trading Concepts",
                       "16 — July 2017 ICT Megatrades", "17 — August 2017 ICT Top Down Analysis", "18 — ICT Order Block Final Guide",
                       "19 — Trendline Savdo Strategiyasi", "20 — Trend chiziqlari", "21 — Trend savdo qilish strategiyasi",
                       "22 — Trend kanallari", "23 — Parabolic SAR", "24 — M&W Trendline Trading Strategy",
                       "25 — Fibo Musang Final BOBI / Home Course", "26 — Fibo Musang Elite", "27 — Fibonacci for the Active Trader",
                       "28 — The Advanced Guide to Fibonacci Trading", "29 — Fibonacci Trading: Time and Price Advantage", "30 — Fibonachchi Darajalari 2-qism",
                       "31 — Rahsia Fibo Musang 2011–2015", "32 — The Most Powerful Setup of Fibo Musang / 6 Setups"],
                   "book_routing":[
                       {"books":"01,08-18","module":"ICT","focus":"liquidity, HTF cycle, macro, killzones, PD arrays, OB/FVG, SMT, COT, OI, day/swing models"},
                       {"books":"02","module":"SMC","focus":"BOS/CHoCH, liquidity, IDM, POI, OB/FVG, LTF confirmation"},
                       {"books":"03","module":"Algo/SMC","focus":"AMD, money transfer, strong/weak H/L, fake BMS/FMS, HVI, breaker/rejection, 90M"},
                       {"books":"01","module":"MSAI","focus":"Malaysian SNR, fresh/unfresh, wick/MISS, engulfing, QML/HNS, storyline"},
                       {"books":"05-06,18","module":"ICT / Risk","focus":"liquidity sweep, MSS/CHoCH, FVG, OB variants, RR and validation"},
                       {"books":"19-24","module":"Trend + Trend Channel","focus":"trendline, channel, trend strength, S/R confluence, MTF, MA, PSAR, reversal candles, risk"},
                       {"books":"25-32","module":"Fibonacci","focus":"Fibo Musang CBR/Initial Break/Dominant Candle/261-423 + retracement/extension/projection + price clusters + time-price confluence + volatility filter + 50% Pin Bar"},
                   ],
                   "strategy_engine":"SIGNALX — YANGI STRATEGIYA","strategy_version":"V1.0"}
    candle_time=selected_data[-2].get("time") if len(selected_data)>1 else selected_data[-1].get("time")
    ai=await ai_validate_module_signal("Yangi Strategiya",key,selected,candle_time,deterministic)
    live_ai=str(ai.get("mode") or "") not in {"fallback","rule_based","unavailable"}
    ai_passed=bool(live_ai and ai.get("validation") and str(ai.get("signal")).upper()==str(deterministic.get("signal")).upper() and int(ai.get("confidence",0))>=85 and int(ai.get("agreement",0))>=70)
    final=deterministic.copy(); final["ai_validation"]=ai; final["ai_gate"]={"required":True,"passed":ai_passed,"minimum_confidence":85,"minimum_agreement":70,"live_ai_required":True}
    if final.get("signal") in {"BUY","SELL"} and not ai_passed:
        final["signal"]="WAIT"; final["entry"]=None; final["stop_loss"]=None; final["take_profit"]=[]; final["state"]="WAIT_AI_VALIDATION"; final["reason"] += "; AI validation required"
    else: final["state"]="AI_CONFIRMED" if final.get("signal") in {"BUY","SELL"} else "WAIT"
    final["current_price"]=round(price,5); final["candle_time"]=candle_time; final["errors"]=errors; final["generated_at"]=datetime.now(timezone.utc).isoformat()
    return {"ok":True,"symbol":key,"selected":selected,"strategy":final,"generated_at":final["generated_at"]}

@app.get("/api/v1/trend-channel/{symbol:path}")
async def get_trend_channel_strategy(symbol: str, interval: str = Query("5min")) -> dict[str, Any]:
    try:
        return await build_trend_channel_strategy(clean_symbol(symbol), validate_interval(interval))
    except Exception as exc:
        return {"ok":False,"symbol":clean_symbol(symbol),"error":str(exc),"generated_at":datetime.now(timezone.utc).isoformat()}

@app.get("/api/v1/fibonacci/{symbol:path}")
async def get_fibonacci_strategy(symbol: str, interval: str = Query("5min")) -> dict[str, Any]:
    try:
        return await build_fibonacci_strategy(clean_symbol(symbol), validate_interval(interval))
    except Exception as exc:
        return {"ok":False,"symbol":clean_symbol(symbol),"error":str(exc),"generated_at":datetime.now(timezone.utc).isoformat()}

@app.get("/api/v1/new-strategy/{symbol:path}")
async def get_new_strategy(symbol: str, interval: str = Query("5min")) -> dict[str, Any]:
    try:
        return await build_book_fusion_strategy(clean_symbol(symbol), validate_interval(interval))
    except Exception as exc:
        return {"ok":False,"symbol":clean_symbol(symbol),"error":str(exc),"generated_at":datetime.now(timezone.utc).isoformat()}

def _pattern_score_band(score: float) -> str:
    s=float(score or 0)
    if s >= 93: return "VERY_STRONG"
    if s >= 85: return "STRONG"
    if s >= 75: return "NORMAL"
    if s >= 60: return "WEAK"
    return "WAIT"


def _finalize_pattern_result(raw: dict[str, Any], candles_by_tf: dict[str, list[dict[str, Any]]], interval: str) -> dict[str, Any]:
    """Turn a deterministic book-style pattern detection into a SignalX pattern candidate.

    Pattern is the trigger. AI is a confirmation/filter. TP2 and RR are informational;
    the hard execution gate later checks geometry, TP1 validity and independent risk.
    """
    out=dict(raw or {})
    out["source"]="Patterns"
    out["strategy_engine"]="SignalX Pattern AI Strategy"
    out["strategy_version"]="P1"
    best=out.get("best") if isinstance(out.get("best"),dict) else None
    if not best or out.get("signal") not in {"BUY","SELL"}:
        out.update({"signal":"WAIT","ai_validation":None,"smart_validation":None,
                    "pattern_score_band":_pattern_score_band(out.get("confidence",0)),
                    "auto_trade_ready":False})
        return out
    direction=str(out.get("signal")).upper()
    # Final Pattern score requirements from the strategy spec.
    raw_score=float(best.get("raw_score") or out.get("confidence") or 0)
    mtf=best.get("mtf_alignment") if isinstance(best.get("mtf_alignment"),dict) else {}
    aligned=mtf.get("state")=="ALIGNED"
    breakout=best.get("breakout") if isinstance(best.get("breakout"),dict) else {}
    hard_pattern_ok=bool(best.get("pattern_valid")) and bool(breakout.get("confirmed")) and raw_score>=85 and aligned
    out["confidence"]=int(min(100,max(0,raw_score)))
    out["pattern_score"]=int(min(100,max(0,raw_score)))
    out["pattern_score_band"]=_pattern_score_band(raw_score)
    out["mtf_alignment"]=mtf
    out["breakout_confirmed"]=bool(breakout.get("confirmed"))
    out["hard_pattern_ok"]=hard_pattern_ok
    out["auto_trade_ready"]=False
    if not hard_pattern_ok:
        out["signal"]="WAIT"
        out["reason"]=f"Pattern detected but final gate not passed: score={raw_score:.0f}, MTF={mtf.get('state','MIXED')}, breakout={'YES' if breakout.get('confirmed') else 'NO'}."
        return out
    try:
        live_ai = out.get("ai_validation") or {}
        ai_signal=str(live_ai.get("signal") or "WAIT").upper()
        mode=str(live_ai.get("mode") or "fallback")
        ai_conf=int(live_ai.get("confidence") or 0)
        ai_agree=int(live_ai.get("agreement") or 0)
        is_live=mode not in {"fallback","rule_based"}
        if is_live:
            ai_ok=(ai_signal==direction and ai_conf>=65 and ai_agree>=55)
            combined=round(raw_score*0.70 + ai_conf*0.30)
        else:
            ai_ok=True
            combined=round(raw_score)
        out["ai_consensus"]="CONFIRMED" if ai_ok else "CONFLICT"
        out["ai_score"]=ai_conf
        out["agreement"]=ai_agree
        out["final_score"]=int(min(100,max(0,combined)))
        out["signal"]=direction if ai_ok else "WAIT"
        out["auto_trade_ready"]=bool(ai_ok)
        out["reason"]=f"{best.get('name')} confirmed by breakout + MTF alignment; AI {'confirmed' if ai_ok else 'rejected'} the setup."
    except Exception:
        out["signal"]="WAIT"
        out["auto_trade_ready"]=False
    return out


async def build_pattern_signals(symbol: str, selected_interval: str = "5min", include_ai_for_selected: bool = True) -> dict[str, Any]:
    """Book-pattern engine on canonical live candles, with optional AI validation for the selected TF."""
    symbol=clean_symbol(symbol)
    selected_interval=validate_interval(selected_interval)
    order=["1min","5min","15min","30min","1h","4h","1day"]
    live_by_tf: dict[str,list[dict[str,Any]]] = {}
    async def load(tf: str):
        try:
            c,_,_=await get_candles(symbol,tf,260)
            live_by_tf[tf]=c
        except Exception:
            live_by_tf[tf]=[]
    await asyncio.gather(*(load(tf) for tf in order))
    frames={}
    for tf in order:
        c=live_by_tf.get(tf) or []
        if len(c)<45:
            frames[tf]={"signal":"WAIT","interval":tf,"patterns":[],"reason":"Insufficient candles"}
            continue
        raw=detect_patterns(c,live_by_tf,tf)
        raw["interval"]=tf
        raw["candle_time"] = c[-2].get("time") if len(c)>1 else c[-1].get("time")
        if include_ai_for_selected and tf==selected_interval and raw.get("signal") in {"BUY","SELL"}:
            ai=await ai_validate_module_signal("Patterns",symbol,tf,raw["candle_time"],raw)
            raw["ai_validation"]=ai
        frames[tf]=_finalize_pattern_result(raw,live_by_tf,tf)
    # If selected 5M had no signal, still preserve its AI status as null; the UI shows the raw detector state.
    best_candidates=[x for x in frames.values() if x.get("signal") in {"BUY","SELL"}]
    selected=frames.get(selected_interval) or {"signal":"WAIT"}
    return {"ok":True,"symbol":symbol,"selected":selected_interval,"timeframes":frames,
            "best":max(best_candidates,key=lambda x:float(x.get("final_score") or x.get("pattern_score") or x.get("confidence") or 0),default=None),
            "generated_at":datetime.now(timezone.utc).isoformat(),
            "strategy":"Pattern trigger + AI confirmation; MTF H4→H1→M30→M15→M5.",
            "notes":["TP1 is primary target.","TP2 is optional/informational.","RR is informational only; it is not an AutoTrade gate.","M1 is history/analysis only and is never AutoTraded."]}


@app.get("/api/v1/patterns/{symbol:path}")
async def get_patterns(symbol: str, interval: str = Query("5min")) -> dict[str, Any]:
    selected=validate_interval(interval)
    try:
        result=await build_pattern_signals(clean_symbol(symbol), selected_interval=selected, include_ai_for_selected=True)
        return result
    except Exception as exc:
        return {"ok":False,"symbol":clean_symbol(symbol),"selected":selected,"timeframes":{},"error":str(exc),"generated_at":datetime.now(timezone.utc).isoformat()}



def _target_candidates_from_item(item: dict[str, Any], direction: str) -> list[float]:
    """Collect structural targets supplied by a module, in directional order."""
    vals: list[float] = []
    def add(v: Any):
        try:
            if v is not None:
                vals.append(float(v))
        except (TypeError, ValueError):
            pass
    def walk(v: Any):
        if isinstance(v, dict):
            for key, value in v.items():
                k=str(key).lower()
                if any(x in k for x in ("resistance", "support", "target", "take_profit", "tp", "extension", "r1", "r2", "r3", "s1", "s2", "s3")):
                    if isinstance(value, (list, tuple)):
                        for x in value: walk(x)
                    elif isinstance(value, dict):
                        walk(value)
                    else: add(value)
                elif isinstance(value, (dict, list, tuple)):
                    walk(value)
        elif isinstance(v, (list, tuple)):
            for x in v: walk(x)
    walk(item)
    # De-duplicate while preserving numeric order later.
    out=[]; seen=set()
    for v in vals:
        key=round(v,4)
        if key not in seen:
            seen.add(key); out.append(v)
    return out


def _structural_target_ladder(item: dict[str, Any], candles: list[dict[str, Any]], direction: str, entry: float, atr_now: float) -> list[float]:
    """Find the next real structural targets; never invent a target from risk math."""
    candidates=_target_candidates_from_item(item,direction)
    # Always include the live pivot ladder so a stale/invalid R1/S1 is skipped in
    # favour of the next valid resistance/support (R2/R3 or S2/S3).
    try:
        ref=candles[-2] if len(candles)>1 else candles[-1]
        levels=calculate_pivot_levels(float(ref["high"]),float(ref["low"]),float(ref["close"]),entry)
        candidates.extend([levels.get("r1"), levels.get("r2"), levels.get("r3")] if direction=="BUY" else [levels.get("s1"), levels.get("s2"), levels.get("s3")])
    except Exception:
        pass
    if direction=="BUY":
        candidates=[v for v in candidates if v is not None and v>entry]
    else:
        candidates=[v for v in candidates if v is not None and v<entry]
    # Add recent confirmed swing levels as fallback resistance/support.
    try:
        lookback=candles[-80:-1] if len(candles)>2 else candles
        highs=sorted({round(float(c["high"]),4) for c in lookback if float(c["high"])>entry}, reverse=False)
        lows=sorted({round(float(c["low"]),4) for c in lookback if float(c["low"])<entry}, reverse=True)
        candidates.extend(highs if direction=="BUY" else lows)
    except Exception:
        pass
    # Filter out levels too close to entry to avoid treating noise as a target.
    min_gap=max(atr_now*0.20, abs(entry)*0.00025)
    candidates=[v for v in candidates if abs(v-entry)>=min_gap]
    if direction=="BUY":
        candidates=sorted(set(round(v,4) for v in candidates))
    else:
        candidates=sorted(set(round(v,4) for v in candidates), reverse=True)
    return candidates[:2]


def _normalize_auto_trade_levels(item: dict[str, Any], candles: list[dict[str, Any]], direction: str, interval: str | None = None) -> tuple[float, float, list[float], bool]:
    """Prepare execution levels after geometry has passed.

    IMPORTANT: this function does not repair a wrong-side Entry/SL. Geometry is a
    hard gate and is checked by _execution_gate before this function is called.
    A missing SL may still be derived from recent structure; an existing invalid SL
    is never silently moved to make a bad signal tradable. Invalid/missing targets are
    handled separately by searching the next structural resistance/support.
    """
    if not candles:
        raise MarketDataError("No live candles available for auto-trade levels")
    current=float(candles[-1]["close"])
    avg_range=sum(abs(float(c["high"])-float(c["low"])) for c in candles[-20:])/max(1,min(20,len(candles)))
    atr_now=max(avg_range,current*0.00015)
    try: entry=float(item.get("entry")) if item.get("entry") is not None else current
    except Exception: entry=current
    repaired=False
    if entry<=0 or abs(entry-current)>max(atr_now*2.5,current*0.0025):
        entry=current; repaired=True
    try: sl=float(item.get("stop_loss")) if item.get("stop_loss") is not None else None
    except Exception: sl=None
    if sl is None:
        if direction=="BUY":
            lows=[float(c["low"]) for c in candles[-5:]]
            buf=max(atr_now*1.15,entry*0.0005)
            sl=min(lows)-buf
        else:
            highs=[float(c["high"]) for c in candles[-5:]]
            buf=max(atr_now*1.15,entry*0.0005)
            sl=max(highs)+buf
        repaired=True

    try: original_tps=[float(v) for v in (item.get("take_profit") or []) if v is not None]
    except Exception: original_tps=[]
    if direction=="BUY":
        valid_original=sorted({round(v,4) for v in original_tps if v>entry})
    else:
        valid_original=sorted({round(v,4) for v in original_tps if v<entry}, reverse=True)
    if valid_original:
        return round(entry,4),round(sl,4),valid_original[:2],repaired

    # Invalid/missing TP: skip R1/S1 when it is on the wrong side and search the
    # next valid structural resistance/support (R2/R3, S2/S3, Fib, swings).
    structural=_structural_target_ladder(item,candles,direction,entry,atr_now)
    return round(entry,4),round(sl,4),structural,repaired


def _execution_gate(item: dict[str, Any], direction: str, candles: list[dict[str, Any]]) -> dict[str, Any]:
    """Hard execution gate: Geometry -> Target -> Risk.

    Returns a machine-readable decision. No failed gate is allowed into MT5.
    """
    direction=str(direction or "WAIT").upper()
    if direction not in {"BUY","SELL"}:
        return {"ok":False,"state":"WAIT","reason":"NO_DIRECTION"}
    if not candles:
        return {"ok":False,"state":"CANCELLED","reason":"NO_LIVE_CANDLES"}

    # Geometry is checked against the module's original values BEFORE any repair.
    try: entry=float(item.get("entry")) if item.get("entry") is not None else None
    except Exception: entry=None
    try: sl=float(item.get("stop_loss")) if item.get("stop_loss") is not None else None
    except Exception: sl=None
    try: raw_tps=[float(v) for v in (item.get("take_profit") or []) if v is not None]
    except Exception: raw_tps=[]

    if entry is not None and sl is not None:
        geometry_ok=(sl < entry) if direction=="BUY" else (sl > entry)
        if not geometry_ok:
            return {"ok":False,"state":"CANCELLED","reason":"INVALID_LEVEL_GEOMETRY",
                    "entry":entry,"sl":sl,"tp":raw_tps,"r_multiple":None}
    if any(v<=0 for v in ([entry] if entry is not None else [])+[sl] if v is not None):
        return {"ok":False,"state":"CANCELLED","reason":"INVALID_LEVEL_GEOMETRY","r_multiple":None}
    if entry is not None:
        bad_tp=any((v<=entry if direction=="BUY" else v>=entry) for v in raw_tps)
        # Wrong-side TP is not itself a cancellation: Target Check will search the
        # next valid structural level.
    else:
        bad_tp=False

    # Normalize levels only after geometry has passed.
    entry2, sl2, tp, repaired = _normalize_auto_trade_levels(item,candles,direction)
    if not tp:
        return {"ok":False,"state":"TARGET_REACHED","reason":"TARGET_REACHED",
                "entry":entry2,"sl":sl2,"tp":[],"repaired":repaired,"r_multiple":None}

    # Risk gate uses the exact SL/TP that will be sent to MT5.
    avg_range=sum(abs(float(c["high"])-float(c["low"])) for c in candles[-20:])/max(1,min(20,len(candles)))
    atr_now=max(avg_range,entry2*0.00015)
    risk=abs(entry2-sl2)
    max_risk=max(atr_now*2.5,entry2*0.0015)
    if risk<=0 or risk>max_risk:
        return {"ok":False,"state":"CANCELLED","reason":"RISK_CHECK_FAILED",
                "entry":entry2,"sl":sl2,"tp":tp,"repaired":repaired,"r_multiple":None,
                "risk":risk,"max_risk":max_risk}
    if direction=="BUY":
        rr=(tp[0]-entry2)/risk
    else:
        rr=(entry2-tp[0])/risk
    # History may keep a valid signal even when its RR is below the AutoTrade minimum.
    # The MT5 queue is stricter and requires RR >= 1.50 before placing the order.
    return {"ok":True,"state":"READY","reason":"ALL_GATES_PASSED",
            "entry":entry2,"sl":sl2,"tp":tp,"repaired":repaired,"r_multiple":rr,
            "risk":risk,"max_risk":max_risk,"autotrade_rr_ok":bool(rr>=1.50)}



def _m5_htf_bias(candles: list[dict[str, Any]]) -> str:
    """Conservative HTF bias: EMA alignment + confirmed swing structure."""
    if len(candles) < 55:
        return "NEUTRAL"
    closes=[float(c["close"]) for c in candles]
    price=closes[-1]
    e20=_ema(closes[-80:],20)
    e50=_ema(closes[-120:],50)
    highs,lows=_ict_swings(candles[:-1],2)
    bull=len(highs)>=2 and len(lows)>=2 and highs[-1][1]>highs[-2][1] and lows[-1][1]>lows[-2][1]
    bear=len(highs)>=2 and len(lows)>=2 and highs[-1][1]<highs[-2][1] and lows[-1][1]<lows[-2][1]
    if bull and e20>e50 and price>e20: return "BULLISH"
    if bear and e20<e50 and price<e20: return "BEARISH"
    if e20>e50 and price>e20: return "BULLISH"
    if e20<e50 and price<e20: return "BEARISH"
    return "NEUTRAL"


def _m5_recent_liquidity_sweep(candles: list[dict[str, Any]], lookback: int = 18) -> dict[str, Any]:
    """Find a recent M5 swing liquidity sweep, preferring the newest event."""
    if len(candles) < 25:
        return {"type":"NONE","level":None,"extreme":None,"index":None}
    highs,lows=_ict_swings(candles[:-2],2)
    start=max(0,len(candles)-lookback-8)
    recent_h=[x for x in highs if x[0]>=start]
    recent_l=[x for x in lows if x[0]>=start]
    for i in range(len(candles)-2, max(1,len(candles)-6), -1):
        c=candles[i]; hi=float(c["high"]); lo=float(c["low"]); close=float(c["close"])
        if recent_l:
            level=recent_l[-1][1]
            if lo < level and close > level:
                return {"type":"SSL_SWEEP","level":level,"extreme":lo,"index":i}
        if recent_h:
            level=recent_h[-1][1]
            if hi > level and close < level:
                return {"type":"BSL_SWEEP","level":level,"extreme":hi,"index":i}
    return {"type":"NONE","level":None,"extreme":None,"index":None}


def _m5_zone_near(price: float, zone: dict[str, Any], atr_value: float, max_atr: float = 0.45) -> bool:
    if not zone or zone.get("low") is None or zone.get("high") is None:
        return False
    lo=float(zone["low"]); hi=float(zone["high"])
    return (lo-max_atr*atr_value) <= price <= (hi+max_atr*atr_value)


def _m5_strategic_pro(c5: list[dict[str, Any]], c15: list[dict[str, Any]],
                      c1h: list[dict[str, Any]], c4h: list[dict[str, Any]]) -> dict[str, Any]:
    """M5 Strategic Pro: HTF bias -> liquidity sweep -> MSS/BOS -> displacement -> OB/FVG retest -> RR.

    This is an AutoTrade gate, not a prediction guarantee. It intentionally prefers WAIT
    over forcing a setup when institutional-style confluence is incomplete.
    """
    if min(len(c5),len(c15),len(c1h),len(c4h)) < 60:
        return {"signal":"WAIT","score":0,"confidence":0,"reason":"Insufficient M5/HTF candles","confirmed":False}
    price=float(c5[-1]["close"])
    a5=max(atr(c5),price*0.0002)
    b4=_m5_htf_bias(c4h); b1=_m5_htf_bias(c1h); b15=_m5_htf_bias(c15)
    sweep=_m5_recent_liquidity_sweep(c5)
    # Sweep determines the setup direction; HTF must agree rather than being overridden.
    direction="BUY" if sweep["type"]=="SSL_SWEEP" else "SELL" if sweep["type"]=="BSL_SWEEP" else "WAIT"
    score=0; checks=[]; reasons=[]
    def add(name,pts,ok,reason):
        nonlocal score
        if ok:
            score += pts; checks.append({"name":name,"points":pts,"status":"PASS"}); reasons.append(reason)
        else:
            checks.append({"name":name,"points":0,"status":"MISS"})
    if direction=="WAIT":
        return {"signal":"WAIT","score":0,"confidence":0,"reason":"No fresh M5 liquidity sweep","confirmed":False,
                "bias":{"H4":b4,"H1":b1,"M15":b15}}
    add("H4 Bias",15,(direction=="BUY" and b4=="BULLISH") or (direction=="SELL" and b4=="BEARISH"),f"H4 {b4}")
    add("H1 Bias",15,(direction=="BUY" and b1=="BULLISH") or (direction=="SELL" and b1=="BEARISH"),f"H1 {b1}")
    add("M15 Bias",10,(direction=="BUY" and b15=="BULLISH") or (direction=="SELL" and b15=="BEARISH"),f"M15 {b15}")
    sweep_ok=(direction=="BUY" and sweep["type"]=="SSL_SWEEP") or (direction=="SELL" and sweep["type"]=="BSL_SWEEP")
    add("Liquidity Sweep",15,sweep_ok,f"{sweep['type']} at {sweep['level']}")
    mss,mss_level=_ict_mss(c5,direction)
    add("MSS / CHoCH",10,mss,f"M5 {'bullish' if direction=='BUY' else 'bearish'} structure shift")
    disp,disp_ratio=_ict_displacement(c5,direction)
    add("Displacement",10,disp,f"M5 displacement {disp_ratio:.2f} ATR")
    fvg=_ict_fvg(c5)
    ob=_ict_order_block(c5,direction,a5)
    fvg_ok=fvg.get("type")==('BULLISH' if direction=='BUY' else 'BEARISH') and _m5_zone_near(price,fvg,a5)
    ob_ok=ob.get("type")==('BULLISH' if direction=='BUY' else 'BEARISH') and _m5_zone_near(price,ob,a5)
    add("FVG Retest",5,fvg_ok,f"M5 {fvg.get('type')} FVG retest")
    add("Order Block Retest",5,ob_ok,f"M5 {ob.get('type')} OB retest")
    # Require both structure shift and displacement, plus at least one institutional zone.
    structure_ok=mss and disp and (fvg_ok or ob_ok)
    if not structure_ok:
        return {"signal":"WAIT","score":score,"confidence":score,"confirmed":False,
                "reason":"; ".join(dict.fromkeys(reasons)) or "Incomplete M5 structure", "checks":checks,
                "bias":{"H4":b4,"H1":b1,"M15":b15},"liquidity":sweep,
                "fvg":fvg,"order_block":ob,"mss":mss,"displacement":disp}
    # Entry at the retested zone midpoint when possible; otherwise live price.
    zone=ob if ob_ok else fvg if fvg_ok else None
    entry=price if not zone else (float(zone["low"])+float(zone["high"])) / 2.0
    # Structural stop: beyond sweep extreme and/or zone, with a small ATR buffer.
    buffer=a5*0.18
    if direction=="BUY":
        structural=min(float(sweep["extreme"]), float(zone["low"]) if zone else price-a5)
        sl=structural-buffer
        risk=entry-sl
    else:
        structural=max(float(sweep["extreme"]), float(zone["high"]) if zone else price+a5)
        sl=structural+buffer
        risk=sl-entry
    if risk <= 0 or risk > a5*2.2:
        return {"signal":"WAIT","score":score,"confidence":score,"confirmed":False,
                "reason":"Structural risk invalid/too wide", "checks":checks,
                "bias":{"H4":b4,"H1":b1,"M15":b15},"liquidity":sweep}
    target=_ict_target_liquidity(c5,direction,entry)
    if direction=="BUY":
        tp1=target if target and target>entry+risk*1.5 else entry+risk*1.5
        tp2=entry+risk*2.5
        if target and target>tp1: tp2=max(tp2,target)
        rr=(tp1-entry)/risk
    else:
        tp1=target if target and target<entry-risk*1.5 else entry-risk*1.5
        tp2=entry-risk*2.5
        if target and target<tp1: tp2=min(tp2,target)
        rr=(entry-tp1)/risk
    add("Risk/Reward (info)",0,True,f"RR {rr:.2f} (informational)")
    confirmed=score>=85
    return {
        "signal":direction if confirmed else "WAIT","score":score,"confidence":min(99,score),"confirmed":confirmed,
        "entry":round(entry,4),"stop_loss":round(sl,4),"take_profit":[round(tp1,4),round(tp2,4)],"risk_reward":round(rr,2),
        "bias":{"H4":b4,"H1":b1,"M15":b15},"liquidity":sweep,"mss":mss,"mss_level":mss_level,
        "displacement":disp,"displacement_atr":round(disp_ratio,2),"fvg":fvg,"order_block":ob,
        "checks":checks,"reason":"; ".join(dict.fromkeys(reasons)),"model":"M5 Strategic Pro",
        "strategy_engine":"SignalX M5 Strategic Pro","strategy_version":"SP1",
        "strategy_chain":["H4 Bias","H1 Bias","M15 Bias","Liquidity Sweep","MSS/CHoCH","Displacement","Order Block/FVG Retest","RR Validation","AutoTrade"],
    }

def _strategic_pro_for_timeframe(interval: str, candles_by_tf: dict[str, list[dict[str, Any]]],
                                  news_blocked: bool = False) -> dict[str, Any]:
    """Dedicated Strategic Pro gate for every timeframe.

    Chain: HTF bias -> session/liquidity -> structure shift -> displacement ->
    OB/FVG proximity -> volatility -> RR. The exact thresholds adapt to TF.
    """
    profile=_strategy_profile(interval)
    candles=candles_by_tf.get(interval) or []
    if len(candles)<40:
        return {"signal":"WAIT","score":0,"confirmed":False,"reason":"Insufficient candles","strategy_engine":"SignalX Strategic Pro","strategy_version":"TF-SP1"}
    price=float(candles[-1]["close"]); a=max(atr(candles),1e-9)
    closes=[float(c["close"]) for c in candles]
    ema_fast=_ema(closes[-100:],20); ema_slow=_ema(closes[-160:],50)
    local_bias="BUY" if ema_fast>ema_slow else "SELL" if ema_fast<ema_slow else "WAIT"
    # Higher-timeframe alignment. Each TF looks to the nearest meaningful parent.
    parent_map={"5min":"15min","15min":"1h","30min":"1h","1h":"4h","4h":"1day","1day":None,"1min":"5min"}
    parent=parent_map.get(interval)
    parent_bias="WAIT"
    if parent and len(candles_by_tf.get(parent) or [])>=40:
        pc=candles_by_tf[parent]; pclose=[float(c["close"]) for c in pc]
        pe20=_ema(pclose[-100:],20); pe50=_ema(pclose[-160:],50)
        parent_bias="BUY" if pe20>pe50 else "SELL" if pe20<pe50 else "WAIT"
    direction=local_bias if local_bias==parent_bias or parent is None else "WAIT"
    checks=[]; reasons=[]; score=0; confirms=0
    def add(name,pts,ok,reason):
        nonlocal score,confirms
        checks.append({"name":name,"ok":bool(ok),"points":pts,"reason":reason})
        if ok: score+=pts; confirms+=1
        else: reasons.append(reason)
    add("Local Trend",12,direction in {"BUY","SELL"},f"{interval} trend={local_bias}")
    add("HTF Bias",15,direction in {"BUY","SELL"} and (parent is None or parent_bias==direction),f"parent={parent or 'none'} bias={parent_bias}")
    # Session filter: active only during liquid London/NY overlap windows in UTC.
    now=candles[-1].get("time")
    session_ok=True
    try:
        dt=datetime.fromisoformat(str(now).replace("Z","+00:00")) if now else datetime.now(timezone.utc)
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        h=dt.astimezone(timezone.utc).hour
        session_ok=(7<=h<17)
    except Exception: pass
    # For 4H/D1, session timing is not a hard filter.
    if interval in {"5min","15min","30min","1h"}:
        add("Liquid Session",8,session_ok,"London/NY liquid session" if session_ok else "Outside liquid London/NY window")
    else:
        add("Session Context",5,True,"Higher timeframe session-neutral")
    # Sweep against recent structure.
    lb={"1min":12,"5min":18,"15min":20,"30min":24,"1h":30,"4h":36,"1day":40}.get(interval,20)
    recent=candles[-(lb+2):-1] if len(candles)>lb+2 else candles[:-1]
    rh=max(float(c["high"]) for c in recent); rl=min(float(c["low"]) for c in recent)
    last=candles[-1]; high=float(last["high"]); low=float(last["low"]); close=float(last["close"]); op=float(last["open"])

    # Confirmation events are allowed to occur in a short recent window instead of
    # requiring every institutional event to happen on the exact same candle. This
    # preserves the strict ensemble while preventing a practically-zero signal rate.
    sweep_window=candles[-4:-1] if len(candles)>=4 else candles[:-1]
    sweep=False
    if direction=="BUY":
        for sc in sweep_window:
            if float(sc["low"]) < rl and float(sc["close"]) > rl:
                sweep=True; break
    elif direction=="SELL":
        for sc in sweep_window:
            if float(sc["high"]) > rh and float(sc["close"]) < rh:
                sweep=True; break
    add("Liquidity Sweep",15,sweep,"recent bullish/bearish liquidity sweep")

    # Structure shift: a directional close break seen within the last 3 completed bars.
    bos=False
    for idx in range(max(1,len(candles)-4), len(candles)):
        cc=candles[idx]
        struct=candles[max(0,idx-7):idx]
        if not struct:
            continue
        sh=max(float(c["high"]) for c in struct); ss=min(float(c["low"]) for c in struct)
        cc_close=float(cc["close"])
        if direction=="BUY" and cc_close>sh:
            bos=True; break
        if direction=="SELL" and cc_close<ss:
            bos=True; break
    add("BOS / CHoCH",12,bos,"recent directional structure break")

    # Displacement: any recent completed candle can provide the impulse.
    body=abs(close-op)
    disp_req={"1min":0.75,"5min":0.95,"15min":1.0,"30min":1.05,"1h":1.10,"4h":1.15,"1day":1.20}.get(interval,1.0)
    displacement=False; best_disp=0.0
    for dc in candles[-4:-1] if len(candles)>=4 else candles[:-1]:
        dc_body=abs(float(dc["close"])-float(dc["open"])) / a
        best_disp=max(best_disp,dc_body)
        if dc_body>=disp_req and ((float(dc["close"])>float(dc["open"])) if direction=="BUY" else (float(dc["close"])<float(dc["open"])) if direction=="SELL" else False):
            displacement=True
    add("Displacement",10,displacement,f"recent best body={best_disp:.2f} ATR; need {disp_req:.2f}")

    # OB/FVG confirmation can also be recent (last 5 completed candles).
    zone_ok=False
    for idx in range(max(2,len(candles)-6), len(candles)-1):
        c1,c2,c3=candles[idx-2],candles[idx-1],candles[idx]
        c3_open=float(c3["open"]); c3_close=float(c3["close"])
        bull_fvg=float(c3["low"])>float(c1["high"]); bear_fvg=float(c3["high"])<float(c1["low"])
        ob_body=abs(c3_close-c3_open)
        ob_bull=float(c2["close"])<float(c2["open"]) and c3_close>c3_open and ob_body>=a*0.8
        ob_bear=float(c2["close"])>float(c2["open"]) and c3_close<c3_open and ob_body>=a*0.8
        if (direction=="BUY" and (bull_fvg or ob_bull)) or (direction=="SELL" and (bear_fvg or ob_bear)):
            zone_ok=True; break
    add("OB / FVG",10,zone_ok,"recent institutional zone/imbalance confirmation")
    # Volatility must be tradable, not dead market or extreme shock.
    ranges=[abs(float(c["high"])-float(c["low"])) for c in candles[-20:]]
    avg_range=sum(ranges)/max(len(ranges),1); vol_ratio=avg_range/a
    vol_ok=0.55<=vol_ratio<=2.75
    add("Volatility",5,vol_ok,f"range/ATR={vol_ratio:.2f}")
    # News is a hard block for lower TFs; higher TF keeps the setup visible but no AutoTrade.
    if news_blocked and interval in {"5min","15min","30min"}:
        add("News Guard",8,False,"high-impact news blackout")
    else:
        add("News Guard",8,True,"news clear / higher-TF context")
    confirmed=(direction in {"BUY","SELL"} and score>=profile["min_score"] and confirms>=profile["min_confirmations"] and not (news_blocked and interval in {"5min","15min","30min"}))
    # Structural risk + informational RR.
    # RR is reported for analytics only and is NOT an AutoTrade eligibility gate.
    if direction=="BUY":
        sl=min(rl,float(c2["low"]),float(last["low"]))-a*0.18; risk=price-sl
        target=rh
    elif direction=="SELL":
        sl=max(rh,float(c2["high"]),float(last["high"]))+a*0.18; risk=sl-price
        target=rl
    else: sl=price; target=price; risk=0
    risk_ok=0<risk<=a*profile["max_risk_atr"]
    if direction=="BUY" and risk_ok:
        t1=max(price+risk*1.5,target); t2=max(price+risk*2.5,t1+risk*0.5)
        rr=(t1-price)/max(risk,1e-9)
    elif direction=="SELL" and risk_ok:
        t1=min(price-risk*1.5,target); t2=min(price-risk*2.5,t1-risk*0.5)
        rr=(price-t1)/max(risk,1e-9)
    else:
        t1=t2=price; rr=0
    add("Structural Risk",5,risk_ok,f"risk={risk/a:.2f} ATR")
    # RR is informational only; it does not decide whether a valid signal is tradable.
    add("Risk/Reward (info)",0,True,f"execution RR={rr:.2f} (informational)")
    confirmed=confirmed and risk_ok
    direction_out=direction if confirmed else "WAIT"
    return {"signal":direction_out,"score":score,"confidence":min(99,score),"confirmed":confirmed,
            "entry":round(price,4),"stop_loss":round(sl,4),"take_profit":[round(t1,4),round(t2,4)],"risk_reward":round(rr,2),
            "strategy_engine":"SignalX Strategic Pro","strategy_version":"TF-SP1","timeframe":interval,
            "profile":profile,"parent_timeframe":parent,"parent_bias":parent_bias,"local_bias":local_bias,
            "checks":checks,"reason":"; ".join(dict.fromkeys(reasons)) or "All Strategic Pro gates passed",
            "session_filter":session_ok,"volatility_ratio":round(vol_ratio,2)}

def _autotrade_source_excluded(source: str) -> bool:
    # Retired legacy sources are never forwarded to AutoTrade.
    normalized = re.sub(r"[\s_\-/]+", " ", str(source or "").strip().lower()).strip()
    blocked = {
        "book + openai", "book openai", "book/openai", "book-openai",
        "signal lab", "algotrade", "signals", "signal engine",
    }
    return normalized in blocked or "book" in normalized and "openai" in normalized


def _queue_autotrade_order(*, symbol: str, source: str, interval: str, direction: str,
                           entry: float, sl: float, tp: list[float], volume: float,
                           confidence: float | None, candle_time: str,
                           risk_reward: float | None = None) -> dict[str, Any] | None:
    """Put one eligible signal into the in-memory MT5 queue exactly once.

    The queue key is symbol/source/timeframe/live-candle/direction. Retired modules are
    explicitly excluded. All values are copied from the freshly validated signal.
    """
    if not MT5_AUTO_TRADING or _autotrade_source_excluded(source):
        return None
    # AutoTrade hard filter: only setups with RR >= 1.50 may reach MT5.
    # Calculate it from the final levels when the caller did not provide it, so no
    # execution path can bypass the minimum by omitting the metadata.
    try:
        rr_eval = float(risk_reward) if risk_reward is not None else None
        if rr_eval is None:
            risk_abs = abs(float(entry) - float(sl))
            first_tp = float(tp[0]) if tp else None
            if risk_abs <= 0 or first_tp is None:
                return None
            rr_eval = ((first_tp - float(entry)) / risk_abs) if str(direction).upper() == "BUY" else ((float(entry) - first_tp) / risk_abs)
        if rr_eval < 1.50:
            print(f"[AUTO TRADE QUEUE] RR BLOCKED market={symbol} source={source} tf={interval} rr={rr_eval:.2f}")
            return None
    except Exception:
        return None
    # M1 is analysis/history-only. Never allow 1-minute signals into AutoTrade.
    if str(interval).strip().lower() in {"1min", "1m", "m1"}:
        print(f"[AUTO TRADE QUEUE] M1 BLOCKED market={symbol} source={source} tf={interval}")
        return None
    market = _mt5_market_key(symbol)
    if market != "XAU/USD":
        return None
    key = (market, source.strip(), interval, str(candle_time), direction.upper())
    # Once an order for this exact market/source/timeframe/candle/direction is reported
    # successful, do not open the same signal again during the same process lifetime.
    if key in MT5_EXECUTED_KEYS:
        print(f"[AUTO TRADE QUEUE] EXECUTED KEY BLOCKED market={market} source={source} tf={interval} candle={candle_time} dir={direction}")
        return None
    for q in MT5_ORDER_QUEUE:
        qkey = (_mt5_market_key(q.get("symbol") or q.get("market")),
                str(q.get("source") or "").strip(), str(q.get("interval") or ""),
                str(q.get("candle_time") or ""), str(q.get("direction") or "").upper())
        if qkey == key:
            return q
        # Never allow BUY and SELL for the same XAUUSD source/timeframe/candle
        # to coexist in the queue. A live candle may recalculate while open; the
        # first accepted consensus owns that candle until it expires/executes.
        if qkey[:4] == key[:4] and qkey[4] != key[4]:
            print(f"[AUTO TRADE QUEUE] OPPOSITE SIGNAL BLOCKED market={market} source={source} tf={interval} candle={candle_time}")
            return None
    order_id = secrets.token_hex(8)
    order = {
        "id": order_id,
        "symbol": market,
        "market": market,
        "execution_symbol": "XAUUSDm",
        "interval": interval,
        "direction": direction.upper(),
        "entry": float(entry),
        "sl": float(sl),
        "tp": [float(x) for x in tp[:2]],
        "volume": float(volume or MT5_LOT_SIZE),
        "source": source.strip(),
        "confidence": float(confidence or 0),
        "risk_reward": float(rr_eval),
        "candle_time": str(candle_time),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "claimed": False,
        "status": "QUEUED",
        "queue_key": [market, source.strip(), interval, str(candle_time), direction.upper()],
    }
    MT5_ORDER_ATTEMPTS[order_id] = 0
    MT5_ORDER_QUEUE.append(order)
    print(f"[AUTO TRADE QUEUE] QUEUED market={market} source={source} tf={interval} dir={direction} entry={entry} sl={sl} tp={tp}")
    return order

@app.post("/api/v1/signals/auto-record")
async def auto_record_signals(symbol: str = DEFAULT_SYMBOL, interval: str = DEFAULT_INTERVAL, authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    """Forward all active SignalX strategy families into History and the MT5 queue.

    Active sources include Technical Analysis, Classic Trade, Auto Trend Line,
    ICT Signals, AI Smart Analysis, MSAI/SNR, SMC, Algo/SMC, Patterns, Trend Channel Engine,
    Fibonacci and Yangi Strategiya. Removed modules remain blocked. AutoTrade additionally
    requires non-M1, valid geometry/risk, AI/market validation and RR >= 1.50.
    """
    require_admin(authorization, session)
    user = current_user(authorization, session)
    selected_interval = validate_interval(interval)
    requested = clean_symbol(symbol)
    if requested != "XAU/USD":
        raise HTTPException(status_code=404, detail="Only XAU/USD is supported")
    symbols = ["XAU/USD"]
    if not AUTO_ENTRY_ENABLED:
        return {"enabled": False, "count": 0, "queued": 0, "symbols": symbols,
                "excluded_sources": ["Signals", "Signal Engine", "Signal Lab", "AlgoTrade", "Book + OpenAI", "M1 / 1min / 1m"],
                "active_sources": ["Technical Analysis", "Classic Trade", "Auto Trend Line", "ICT Signals", "AI Smart Analysis", "MSAI/SNR", "SMC", "Algo/SMC", "Patterns", "Trend Channel Engine", "Fibonacci", "Yangi Strategiya"],
                "mode": "disabled"}

    now = datetime.now(timezone.utc)
    excluded = {"book + openai", "book/openai", "book-openai", "book openai", "signal lab", "algotrade"}
    created_history = []
    queued = []
    module_signal_count = 0
    seen_queue_keys = set()

    async def load_symbol_candidates(key: str) -> tuple[list[dict[str, Any]], dict[str, tuple[list[dict[str, Any]], str, str | None]]]:
        candidates: list[dict[str, Any]] = []
        # One canonical live candle series per timeframe. Every module below consumes
        # the same timeframe candles, so the signal chain cannot mix symbols or TF data.
        intervals=["5min","15min","30min","1h","4h","1day"]
        live_by_tf: dict[str, tuple[list[dict[str, Any]],str,str|None]] = {}
        async def load_tf(tf: str):
            try:
                live_by_tf[tf]=await get_candles(key,tf,260)
            except Exception:
                live_by_tf[tf]=([],"error",None)
        await asyncio.gather(*(load_tf(tf) for tf in intervals))

        # Patterns is a first-class strategy family: book pattern = trigger, AI = filter.
        # Pattern detection itself is deterministic here; the common process_symbol()
        # layer applies the per-module AI + geometry + target + risk gates before queueing.
        for tf in intervals:
            pc=live_by_tf.get(tf,([],"error",None))[0]
            if len(pc)>=45:
                try:
                    pattern_context={k:v[0] for k,v in live_by_tf.items() if v and v[0]}
                    raw_pattern=detect_patterns(pc,pattern_context,tf)
                    raw_pattern["interval"]=tf
                    raw_pattern["candle_time"]=pc[-2].get("time") if len(pc)>1 else pc[-1].get("time")
                    pattern_item=_finalize_pattern_result(raw_pattern,pattern_context,tf)
                    if pattern_item.get("signal") in {"BUY","SELL"} and pattern_item.get("hard_pattern_ok"):
                        candidates.append({"source":"Patterns","interval":tf,"item":pattern_item,"response":pattern_item})
                except Exception as exc:
                    print(f"[PATTERNS] candidate build error tf={tf}: {type(exc).__name__}: {exc}")

        # Algo/SMC book strategy: deterministic book-derived setup + strict AI validation.
        # It is a first-class family and only emits BUY/SELL when the AI hard gate passes.
        for tf in intervals:
            try:
                if tf not in live_by_tf or len(live_by_tf[tf][0]) < 60:
                    continue
                algo_result = await build_algo_smc_strategy(key, tf, prefetched=live_by_tf)
                algo_item = dict(algo_result.get("strategy") or {})
                if algo_item.get("signal") in {"BUY", "SELL"} and algo_item.get("ai_gate", {}).get("passed"):
                    candidates.append({"source":"Algo/SMC","interval":tf,"item":algo_item,"response":algo_result})
            except Exception as exc:
                print(f"[ALGO/SMC] candidate build error tf={tf}: {type(exc).__name__}: {exc}")

        # MSAI/SNR: deterministic Malaysian-SNR analysis is kept independent from ICT/SMC;
        # the common process layer adds live AI validation before History/AutoTrade.
        for tf in intervals:
            pc=live_by_tf.get(tf,([],"error",None))[0]
            if len(pc)>=60:
                try:
                    daily=live_by_tf.get("1day",([],"error",None))[0]
                    weekly=aggregate_weekly(daily) if daily else []
                    local_mtf={
                        "direction_bias": direction_from_candles(weekly) if len(weekly)>=5 else "NEUTRAL",
                        "alignment": True,
                    }
                    msai_item=analyze_msai(pc,local_mtf,tf)
                    msai_item["interval"]=tf
                    msai_item["candle_time"]=pc[-2].get("time") if len(pc)>1 else pc[-1].get("time")
                    if msai_item.get("signal") in {"BUY","SELL"}:
                        candidates.append({"source":"MSAI/SNR","interval":tf,"item":msai_item,"response":msai_item})
                except Exception as exc:
                    print(f"[MSAI] candidate build error tf={tf}: {type(exc).__name__}: {exc}")

        # SMC: deterministic BOS/CHoCH, liquidity, IDM, POI and LTF framework.
        for tf in intervals:
            pc=live_by_tf.get(tf,([],"error",None))[0]
            if len(pc)>=60:
                try:
                    daily=live_by_tf.get("1day",([],"error",None))[0]
                    weekly=aggregate_weekly(daily) if daily else []
                    bias=direction_from_candles(weekly) if len(weekly)>=5 else "NEUTRAL"
                    smc_mtf={"direction_bias":bias,"alignment":bias in {"BULLISH","BEARISH"}}
                    smc_item=analyze_smc(pc,smc_mtf,tf)
                    smc_item["interval"]=tf
                    smc_item["candle_time"]=pc[-2].get("time") if len(pc)>1 else pc[-1].get("time")
                    if smc_item.get("signal") in {"BUY","SELL"}:
                        candidates.append({"source":"SMC","interval":tf,"item":smc_item,"response":smc_item})
                except Exception as exc:
                    print(f"[SMC] candidate build error tf={tf}: {type(exc).__name__}: {exc}")

        # Trend Channel Engine: use the same canonical candle set; final AI + execution gates
        # are applied once by process_symbol() so History and AutoTrade stay synchronized.
        for tf in intervals:
            pc=live_by_tf.get(tf,([],"error",None))[0]
            if len(pc)>=60:
                try:
                    higher={x:live_by_tf.get(x,([],"error",None))[0] for x in ("1day","4h","1h")}
                    tc_item=analyze_trend_channel(pc,higher)
                    tc_item["interval"]=tf
                    tc_item["candle_time"]=pc[-2].get("time") if len(pc)>1 else pc[-1].get("time")
                    if tc_item.get("signal") in {"BUY","SELL"}:
                        candidates.append({"source":"Trend Channel Engine","interval":tf,"item":tc_item,"response":tc_item})
                except Exception as exc:
                    print(f"[TREND CHANNEL] candidate build error tf={tf}: {type(exc).__name__}: {exc}")

        # Yangi Strategiya: all-book fusion (32 supplied sources), using the same canonical
        # candles already loaded. It is its own independent strategy family.
        for tf in intervals:
            try:
                raw_prefetched={k:v for k,v in live_by_tf.items() if v and v[0]}
                fusion_result=await build_book_fusion_strategy(key,tf,prefetched=raw_prefetched)
                fusion_item=dict(fusion_result.get("strategy") or {})
                if fusion_item.get("signal") in {"BUY","SELL"}:
                    candidates.append({"source":"Yangi Strategiya","interval":tf,"item":fusion_item,"response":fusion_result})
            except Exception as exc:
                print(f"[YANGI STRATEGIYA] candidate build error tf={tf}: {type(exc).__name__}: {exc}")

        # Fibonacci is a first-class strategy family from books 25–32.
        # It uses the same canonical candles already loaded above, then the common
        # process_symbol() layer applies the strict per-module AI + execution gates.
        for tf in intervals:
            pc=live_by_tf.get(tf,([],"error",None))[0]
            if len(pc)>=60:
                try:
                    fib_context={k:v[0] for k,v in live_by_tf.items() if v and v[0]}
                    fib_item=analyze_fibonacci(pc,{"1day":fib_context.get("1day",[]),"4h":fib_context.get("4h",[]),"1h":fib_context.get("1h",[])})
                    fib_item["interval"]=tf
                    fib_item["candle_time"]=pc[-2].get("time") if len(pc)>1 else pc[-1].get("time")
                    if fib_item.get("signal") in {"BUY","SELL"}:
                        candidates.append({"source":"Fibonacci","interval":tf,"item":fib_item,"response":fib_item})
                except Exception as exc:
                    print(f"[FIBONACCI] candidate build error tf={tf}: {type(exc).__name__}: {exc}")

        # Remaining modules are evaluated on all supported timeframes.

        for tf in intervals:
            candles, mode, warning = live_by_tf.get(tf,([],"error",None))
            if len(candles)<40:
                continue
            ct=candles[-1].get("time")
            try:
                ref=candles[-2] if len(candles)>1 else candles[-1]
                price=float(candles[-1]["close"])
                levels=calculate_pivot_levels(float(ref["high"]),float(ref["low"]),float(ref["close"]),price)
                technical=build_key_level_signal(candles,levels,news_blocked=False)
                technical=_enhance_strategy_result(technical,candles,tf)
                candidates.append({"source":"Technical Analysis","interval":tf,"item":technical,"response":{"mode":mode,"warning":warning,"candle_time":ct}})
            except Exception:
                technical={}
            try:
                classic=_classic_trade(candles,calculate_pivot_levels(float(candles[-2]["high"]),float(candles[-2]["low"]),float(candles[-2]["close"]),float(candles[-1]["close"])))
                classic["strategy_chain"]=_strategy_chain(tf); classic["strategy_version"]="V2"
                candidates.append({"source":"Classic Trade","interval":tf,"item":classic,"response":{"mode":mode,"warning":warning,"candle_time":ct}})
            except Exception:
                pass
            try:
                trend=_trendline_analysis(candles); fib=_fibonacci_analysis(candles)
                trend["strategy_engine"]="Market Structure Trendline V2"; trend["strategy_version"]="V2"; trend["strategy_chain"]=_strategy_chain(tf)
                trend["take_profit"]=[v for v in [fib.get("extension_targets",{}).get("1.272"),fib.get("extension_targets",{}).get("1.618")] if v is not None]
                candidates.append({"source":"Auto Trend Line","interval":tf,"item":trend,"response":{"mode":mode,"warning":warning,"candle_time":ct,"fibonacci":fib}})
            except Exception:
                pass
            # ICT uses its dedicated M30→M5 structure. For every TF, expose the same
            # canonical ICT result in that TF's chain so AutoTrade can receive any TF.
            try:
                c30=live_by_tf.get("30min",([],"",None))[0]; c5=live_by_tf.get("5min",([],"",None))[0]
                if len(c30)>=40 and len(c5)>=40:
                    ict=build_ict_m30_m5(c30,c5); ict["interval"]=tf; ict["strategy_engine"]="ICT M30→M5 V2"; ict["strategy_version"]="V2"; ict["strategy_chain"]=_strategy_chain(tf)
                    candidates.append({"source":"ICT Signals","interval":tf,"item":ict,"response":{"mode":"tradingview","candle_time":ct}})
            except Exception:
                pass
            # AI Smart Analysis remains chained to the same TF's technical result plus MTF context.
            try:
                mtf=await multi_timeframe(key)
                smart={"signal":technical.get("signal","WAIT"),"confidence":technical.get("confidence",0),"entry":technical.get("entry"),"stop_loss":technical.get("stop_loss"),"take_profit":technical.get("take_profit",[]),"reason":f"Technical V2 + MTF {mtf.get('overall','MIXED')}","strategy_engine":"Multi-scenario AI Decision V2","strategy_version":"V2","strategy_chain":_strategy_chain(tf),"interval":tf}
                if smart["signal"] in {"BUY","SELL"}:
                    candidates.append({"source":"AI Smart Analysis","interval":tf,"item":smart,"response":{"mode":"confirmation-only","multi_timeframe":mtf,"candle_time":ct}})
            except Exception:
                pass
        return candidates, live_by_tf

    def _build_consensus(candidates: list[dict[str, Any]], interval: str, candle_time: str) -> dict[str, Any] | None:
        """Collapse all module outputs into ONE directional decision per XAU timeframe/candle.

        Active strategy modules are counted as independent families. Retired modules never
        enter consensus; ties, conflicts and weak consensus become WAIT.
        """
        weights = {
            "Technical Analysis": 1.00,
            "Classic Trade": 1.00,
            "Auto Trend Line": 1.10,
            "ICT Signals": 1.40,
            "AI Smart Analysis": 0.80,
            "MSAI/SNR": 1.20,
            "SMC": 1.30,
            "Algo/SMC": 1.50,
            "Trend Channel Engine": 1.20,
            "Fibonacci": 1.30,
            "Yangi Strategiya": 1.70,
        }
        families: dict[str, dict[str, Any]] = {}
        aliases = {}
        for c in candidates:
            if str(c.get("interval")) != interval:
                continue
            item = c.get("item") or {}
            direction = str(item.get("signal") or item.get("direction") or "WAIT").upper()
            if direction not in {"BUY", "SELL"}:
                continue
            source = str(c.get("source") or "").strip()
            family = aliases.get(source.lower(), source)
            if family not in weights:
                continue
            confidence = max(0.0, min(100.0, float(item.get("confidence") or item.get("trend_power") or 0)))
            # Confidence contributes gradually; no single module can dominate the ensemble.
            score = weights[family] * (0.55 + 0.45 * confidence / 100.0)
            bucket = families.setdefault(family, {"BUY": 0.0, "SELL": 0.0, "items": []})
            bucket[direction] += score
            bucket["items"].append((direction, item, source, confidence))

        if not families:
            return None
        totals = {d: 0.0 for d in ("BUY", "SELL")}
        for f in families.values():
            totals["BUY"] += f["BUY"]
            totals["SELL"] += f["SELL"]
        winner = "BUY" if totals["BUY"] > totals["SELL"] else "SELL" if totals["SELL"] > totals["BUY"] else "WAIT"
        if winner == "WAIT":
            return None
        loser = "SELL" if winner == "BUY" else "BUY"
        active_total = totals[winner] + totals[loser]
        agreement = (totals[winner] / active_total) if active_total else 0.0
        distinct_winner = sum(1 for f in families.values() if f[winner] > 0)
        min_families = 2  # tradable timeframes: require two independent strategy families
        # Hard conflict protection: if the opposing side is materially represented, wait.
        if distinct_winner < min_families or agreement < 0.60 or (active_total and totals[loser] / active_total > 0.35):
            return None
        # Choose the strongest representative setup on the winning side for levels.
        reps=[]
        for f in families.values():
            for d,item,source,conf in f["items"]:
                if d == winner:
                    reps.append((weights.get(aliases.get(source.lower(), source),1.0) * (0.55+0.45*conf/100), item, source, conf))
        reps.sort(key=lambda x:x[0], reverse=True)
        _, representative, rep_source, rep_conf = reps[0]
        return {
            "signal": winner,
            "confidence": round(min(99.0, max(0.0, 50.0 + 50.0 * agreement)), 1),
            "entry": representative.get("entry"),
            "stop_loss": representative.get("stop_loss"),
            "take_profit": representative.get("take_profit") or [],
            "reason": f"Consensus {winner}: {distinct_winner} independent strategy families agreed; agreement {agreement*100:.1f}%.",
            "consensus_agreement": round(agreement*100, 1),
            "consensus_families": sorted(families.keys()),
            "consensus_votes": {f:{"BUY":round(v["BUY"],3),"SELL":round(v["SELL"],3)} for f,v in families.items()},
            "consensus_source": rep_source,
            "consensus_source_confidence": rep_conf,
            "candle_time": candle_time,
            "strategy_engine": "SignalX Consensus Engine V3",
            "strategy_version": "V3",
            "decision_state": "CONFIRMED",
            "strategy_chain": _strategy_chain(interval),
        }

    async def process_symbol(key: str):
        nonlocal created_history, queued, module_signal_count
        candidates, live_by_tf = await load_symbol_candidates(key)
        print(f"[SIGNAL FLOW] candidates={len(candidates)} market={key}")

        # Persist AND queue every confirmed module signal independently.
        # M1 remains excluded; Removed modules are excluded by the common queue guard.
        # Each module gets its own History row and its own AutoTrade queue key.
        # This intentionally does NOT collapse module signals into a single consensus order.
        for c in candidates:
            tf = str(c.get("interval") or "").strip().lower()
            item = dict(c.get("item") or {})
            direction = str(item.get("signal") or item.get("direction") or "WAIT").upper()
            if tf not in {"5min", "15min", "30min", "1h", "4h", "1day"} or direction not in {"BUY", "SELL"}:
                continue
            candles = live_by_tf.get(tf, ([], "error", None))[0]
            if len(candles) < 40:
                continue
            candle_time = _normalize_history_candle_time(candles[-1].get("time"))
            source = _normalize_history_source(c.get("source") or HISTORY_DEFAULT_SOURCE)
            original_direction = direction
            original_item = dict(item)

            # Every AutoTrade-capable module now gets its own AI validation on the
            # same live candle. AI is used as a quality layer, while History keeps
            # the original module signal even when AI rejects AutoTrade.
            try:
                ai = await ai_validate_module_signal(source, key, tf, candle_time, original_item)
            except Exception as exc:
                ai = {"mode":"fallback","signal":original_direction,"confidence":0,"agreement":0,
                      "risk_flags":["AI validation exception"],"reasoning":str(exc)[:240]}
            smart = _smart_module_gate(original_item, ai, candles, original_direction)
            item["ai_validation"] = ai
            item["ai_assisted"] = True
            item["ai_layer"] = f"Per-module AI Validation ({source})"
            item["smart_validation"] = smart

            # Hard pipeline: Signal -> AI/Market Quality -> Geometry -> Target -> Risk -> AutoTrade.
            # AI/market quality failure is History-only; it never deletes the module signal.
            if not smart.get("ok"):
                item.update({"signal":original_direction,"auto_trade_eligible":False,
                             "execution_state":"AI_VALIDATION_FAILED",
                             "execution_reason":smart.get("reason") or "AI_VALIDATION_FAILED",
                             "live_levels_verified":False})
                payload = {"source":source,"module_signal":item,"symbol":key,"interval":tf,
                           "candle_time":candle_time,"live_generated":True,
                           "execution_gate":{"state":"AI_VALIDATION_FAILED","reason":smart.get("reason"),
                                             "ai_checked":True,"geometry_checked":False,"target_checked":False,
                                             "risk_checked":False,"auto_trade":False}}
                recent = session.scalars(select(SignalHistory).where(
                    SignalHistory.user_id == user.id, SignalHistory.symbol == key,
                    SignalHistory.interval == tf, SignalHistory.candle_time == candle_time,
                    SignalHistory.source == source,
                ).order_by(SignalHistory.id.desc())).first()
                if recent is None:
                    history_row = SignalHistory(user_id=user.id,symbol=key,interval=tf,direction=original_direction,
                        headline=f"{source} · {original_direction} · AI {int(ai.get('confidence') or 0)}% · AI VALIDATION",price=float(item.get("entry") or 0),
                        payload=json.dumps(payload,ensure_ascii=False,default=str),outcome="CANCELLED",status="CANCELLED",
                        created_at=now,source=source,candle_time=candle_time)
                    session.add(history_row)
                    created_history.append({"source":source,"symbol":key,"interval":tf,"direction":original_direction,
                                            "confidence":float(item.get("confidence") or item.get("trend_power") or 0),
                                            "module_history":True,"auto_trade_eligible":False,
                                            "execution_state":"AI_VALIDATION_FAILED","reason":smart.get("reason")})
                continue

            # Preserve the module direction; merge only the AI metadata. Since the
            # Smart Gate already required agreement, merge_ai_validation cannot turn
            # a valid candidate into a tradable opposite-side signal.
            item = merge_ai_validation(original_item, ai)
            item["ai_validation"] = ai
            item["ai_assisted"] = True
            item["ai_layer"] = f"Per-module AI Validation ({source})"
            item["smart_validation"] = smart
            direction = original_direction

            # Geometry is checked against the ORIGINAL module values before normalization.
            gate = _execution_gate(item, direction, candles)
            entry = gate.get("entry")
            sl = gate.get("sl")
            tp = list(gate.get("tp") or [])
            repaired = bool(gate.get("repaired"))
            conf = float(item.get("confidence") or item.get("trend_power") or 0)

            if gate.get("state") == "CANCELLED":
                reason = str(gate.get("reason") or "EXECUTION_GATE_FAILED")
                item.update({
                    "signal": direction, "entry": entry, "stop_loss": sl, "take_profit": tp,
                    "auto_trade_eligible": False, "execution_state": "CANCELLED",
                    "execution_reason": reason, "risk_reward": None,
                    "live_levels_verified": True,
                })
                payload = {"source":source,"module_signal":item,"symbol":key,"interval":tf,
                           "candle_time":candle_time,"live_generated":True,
                           "execution_gate":{"state":"CANCELLED","reason":reason,"geometry_checked":True,
                                             "target_checked":True,"risk_checked":True,"auto_trade":False}}
                recent = session.scalars(select(SignalHistory).where(
                    SignalHistory.user_id == user.id, SignalHistory.symbol == key,
                    SignalHistory.interval == tf, SignalHistory.candle_time == candle_time,
                    SignalHistory.source == source,
                ).order_by(SignalHistory.id.desc())).first()
                if recent is None:
                    history_row = SignalHistory(user_id=user.id,symbol=key,interval=tf,direction=direction,
                        headline=f"{source} · {direction} · {conf:.1f}% · {reason}",price=float(entry or 0),
                        payload=json.dumps(payload,ensure_ascii=False,default=str),outcome="CANCELLED",status="CANCELLED",
                        created_at=now,source=source,candle_time=candle_time)
                    session.add(history_row)
                    created_history.append({"source":source,"symbol":key,"interval":tf,"direction":direction,
                                            "confidence":conf,"module_history":True,"auto_trade_eligible":False,
                                            "execution_state":"CANCELLED","reason":reason})
                continue

            target_reached = gate.get("state") == "TARGET_REACHED"
            rr_value = float(gate.get("r_multiple") or 0)
            autotrade_rr_ok = bool(rr_value >= 1.50)
            if target_reached:
                item.update({"signal":"WAIT","original_signal":direction,"setup":"TARGET_REACHED",
                             "entry":entry,"stop_loss":sl,"take_profit":[],"target_state":"TARGET_REACHED",
                             "auto_trade_eligible":False,"execution_state":"TARGET_REACHED",
                             "risk_reward":None,"live_levels_verified":True,"levels_repaired_from_live_chart":repaired})
                direction_history = "WAIT"
            else:
                item.update({"entry":entry,"stop_loss":sl,"take_profit":tp,"live_levels_verified":True,
                             "levels_repaired_from_live_chart":repaired,"auto_trade_eligible":bool(gate.get("ok") and autotrade_rr_ok),
                             "execution_state":"READY","execution_reason":"ALL_GATES_PASSED" if autotrade_rr_ok else "HISTORY_ONLY_RR_BELOW_1.50",
                             "risk_reward":gate.get("r_multiple"),"auto_trade_rr_ok":autotrade_rr_ok})
                direction_history = direction

            payload = {"source":source,"module_signal":item,"symbol":key,"interval":tf,"candle_time":candle_time,
                       "live_generated":True,"execution_gate":{
                           "state":gate.get("state"),"reason":gate.get("reason"),"geometry_checked":True,
                           "target_checked":True,"risk_checked":not target_reached,
                           "auto_trade":bool(gate.get("ok") and autotrade_rr_ok),
                           "risk_reward":gate.get("r_multiple"),"autotrade_rr_min":1.50,
                           "risk":gate.get("risk"),"max_risk":gate.get("max_risk"),
                           "levels_repaired":repaired},"auto_trade":{"queued":False}}
            recent = session.scalars(select(SignalHistory).where(
                SignalHistory.user_id == user.id, SignalHistory.symbol == key,
                SignalHistory.interval == tf, SignalHistory.candle_time == candle_time,
                SignalHistory.source == source,
            ).order_by(SignalHistory.id.desc())).first()
            history_row = None
            if recent is None:
                history_row = SignalHistory(
                    user_id=user.id, symbol=key, interval=tf, direction=direction_history,
                    headline=f"{source} · {direction_history} · {conf:.1f}%", price=float(entry or 0),
                    payload=json.dumps(payload, ensure_ascii=False, default=str),
                    outcome=("TARGET_REACHED" if target_reached else "OPEN"),
                    status=("TARGET_REACHED" if target_reached else "ACTIVE"),
                    created_at=now, source=source, candle_time=candle_time
                )
                session.add(history_row)
                created_history.append({"source":source,"symbol":key,"interval":tf,"direction":direction_history,
                                        "confidence":conf,"module_history":True,
                                        "auto_trade_eligible":bool(gate.get("ok") and autotrade_rr_ok),
                                        "execution_state":gate.get("state"),"risk_reward":gate.get("r_multiple"),
                                        "auto_trade_rr_ok":autotrade_rr_ok})
                print(f"[SIGNAL HISTORY] MODULE RECORDED source={source} market={key} tf={tf} dir={direction_history} state={gate.get('state')}")
            elif str(recent.status or "ACTIVE").upper() in {"ACTIVE","TP1 HIT","OPEN"} and str(recent.outcome or "OPEN").upper() in {"OPEN","TP1 HIT"}:
                recent.direction = direction_history
                recent.price = float(entry or 0)
                recent.headline = f"{source} · {direction_history} · {conf:.1f}%"
                recent.payload = json.dumps(payload, ensure_ascii=False, default=str)
                _history_sync_row(recent, payload)

            order = None
            if direction in {"BUY", "SELL"} and tp and bool(gate.get("ok")) and autotrade_rr_ok:
                order = _queue_autotrade_order(
                    symbol=key, source=source, interval=tf, direction=direction,
                    entry=entry, sl=sl, tp=tp, volume=MT5_LOT_SIZE,
                    confidence=conf, candle_time=candle_time, risk_reward=rr_value,
                )
            if order is not None:
                payload["auto_trade"]["queued"] = True
                target_row = recent if recent is not None else history_row
                if target_row is not None:
                    target_row.payload = json.dumps(payload, ensure_ascii=False, default=str)
                queued.append(order)
                module_signal_count += 1
                print(f"[AUTO TRADE QUEUE] MODULE QUEUED source={source} market={key} tf={tf} dir={direction} candle={candle_time}")

    await asyncio.gather(*(process_symbol(k) for k in symbols))
    if created_history:
        session.commit()
    rows = await refresh_signal_outcomes(session, user.id, limit=80)
    return {
        "enabled": True,
        "symbols": symbols,
        "count": len(created_history),
        "queued": len(queued),
        "module_autotrade_queued": module_signal_count,
        "history_count": len(rows),
        "mode": "mt5_demo_queue" if MT5_AUTO_TRADING else "history_only",
        "forward_mode": "EVERY CONFIRMED ACTIVE MODULE SIGNAL EXCEPT M1; MT5 requires RR >= 1.50",
        "excluded_sources": ["Signals", "Signal Engine", "Signal Lab", "AlgoTrade", "Book + OpenAI", "M1 / 1min / 1m"],
        "active_sources": ["Technical Analysis", "Classic Trade", "Auto Trend Line", "ICT Signals", "AI Smart Analysis", "MSAI/SNR", "SMC", "Algo/SMC", "Patterns", "Trend Channel Engine", "Fibonacci", "Yangi Strategiya"],
        "items": created_history,
        "user_id": int(user.id),
    }


_AUTOTRADE_WORKER_STARTED = False

async def _autotrade_worker() -> None:
    """Generate live BUY/SELL signals into the MT5 queue without browser login."""
    global _AUTOTRADE_WORKER_STARTED
    if _AUTOTRADE_WORKER_STARTED:
        return
    _AUTOTRADE_WORKER_STARTED = True
    await asyncio.sleep(3)
    while True:
        session = SessionLocal()
        try:
            if MT5_AUTO_TRADING and AUTO_ENTRY_ENABLED:
                result = await auto_record_signals(
                    symbol="XAU/USD", interval="5min",
                    authorization=f"Bearer {AUTOTRADE_INTERNAL_TOKEN}", session=session
                )
                queued_count = int(result.get("queued") or 0)
                bridge_user_id = int(result.get("user_id") or 0)
                if not bridge_user_id:
                    admin_user = session.scalar(select(User).where(User.username == os.getenv("ADMIN_LOGIN", "Shohruh")))
                    bridge_user_id = int(admin_user.id) if admin_user else 0
                history_forwarded = _forward_recent_history_to_mt5(session, bridge_user_id) if bridge_user_id else []
                print(f"[AUTO TRADE WORKER] symbols={result.get('symbols')} queued={queued_count} history_forwarded={len(history_forwarded)} queue_total={len(MT5_ORDER_QUEUE)}")
        except Exception as exc:
            print(f"[AUTO TRADE WORKER] error={exc}")
        finally:
            session.close()
        await asyncio.sleep(max(5, int(os.getenv("AUTOTRADE_WORKER_SECONDS", "15"))))


@app.on_event("startup")
async def _start_autotrade_worker() -> None:
    # Always start the worker at application startup.  AutoTrade can be
    # toggled from the site after Railway has already started; the worker
    # itself checks MT5_AUTO_TRADING on every cycle, so OFF means idle and
    # ON immediately resumes signal generation without a redeploy.
    asyncio.create_task(_autotrade_worker())


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
    """Canonicalize broker symbols to a strict transport market key.

    Handles XAUUSD broker suffix variants and separator variants.
    """
    raw = str(symbol or MT5_BRIDGE_STATE.get("symbol") or DEFAULT_SYMBOL).strip().upper()
    compact = raw.replace("/", "").replace("-", "").replace("_", "")
    if compact.startswith("XAUUSD"):
        return "XAU/USD"
    return raw.replace("-", "/")

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
        ai_advisory = await _module_ai_advisory("Trend Line + Fibonacci", key, interval, closed[-1].get("time") if closed else None, {"signal": tl.get("signal", "WAIT"), "trend": tl.get("trend"), "trend_power": tl.get("trend_power", 0), "fibonacci": fib, "reason": tl.get("reason", "")})
        tl["ai_validation"] = ai_advisory
        fib["ai_validation"] = ai_advisory
        tl["strategy_engine"]="Market Structure Trendline Engine"
        tl["market_regime"]=_adaptive_regime(closed)
        tl["strategy_quality"]=int(tl.get("trend_power") or 0)
        return {"symbol": key, "interval": interval, "candles": candles_data[-260:], "trendline": tl, "fibonacci": fib,
                "mode": "mt5", "warning": None, "provider": "Exness MT5", "source": f"MT5 {key} terminal candles",
                "generated_at": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        return {"symbol": key, "interval": interval, "candles": [],
                "trendline": {"available": False, "trend": "NEUTRAL", "type": "NONE", "touches": 0, "trend_power": 0, "breakout": "NO", "retest": "NO", "confirmation": "WAIT", "signal": "WAIT", "reason": str(exc)},
                "fibonacci": {"available": False, "direction": "NEUTRAL", "signal": "WAIT", "reason": str(exc), "levels": {}},
                "mode": "mt5_unavailable", "warning": str(exc), "provider": "Exness MT5",
                "generated_at": datetime.now(timezone.utc).isoformat()}


@app.get("/api/v1/ai-signals/live/{symbol:path}")
async def ai_signals_live(symbol: str, interval: str = DEFAULT_INTERVAL, authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    """Live AI Signals endpoint: current market candle + quantitative engine + AI validation.
    It intentionally calculates only the selected timeframe to keep the dedicated UI fast.
    """
    require_admin(authorization, session)
    key=clean_symbol(symbol); interval=validate_interval(interval)
    candles_data, mode, warning = await get_candles(key, interval, 260)
    if len(candles_data) < 40:
        raise MarketDataError(f"{interval} uchun real signal hisoblashga candle yetarli emas")
    item=build_advanced_signal(candles_data, interval, news_blocked=False)
    candle_time=candles_data[-1].get("time") if candles_data else None
    ai=await ai_validate_module_signal("AI Signals", key, interval, candle_time, item)
    item=merge_ai_validation(item, ai)
    item["candle_time"]=candle_time
    item["mode"]=mode
    item["warning"]=warning
    return {"symbol":key,"interval":interval,"signal":item,"ai_validation":ai,"mode":"live","source":f"TradingView {tv_symbol_for(key)} live candle","generated_at":datetime.now(timezone.utc).isoformat()}


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
    markets: dict[str, dict[str, Any]] = {}
    client_id: str = ""

class MT5ReportBody(BaseModel):
    action: str = ""
    ticket: str = ""
    symbol: str = ""
    status: str = ""
    price: float | None = None
    profit: float | None = None
    message: str = ""
    client_id: str = ""

class ModuleSignalBody(BaseModel):
    symbol: str = DEFAULT_SYMBOL
    interval: str = DEFAULT_INTERVAL
    source: str = HISTORY_DEFAULT_SOURCE
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
    """Persist a module signal using fresh candles for the exact symbol/timeframe.

    Client-supplied Entry/SL/TP are treated as hints only; the server revalidates them
    against the current TradingView chart so history cannot store cross-symbol or stale
    levels.
    """
    user = current_user(authorization, session)
    direction = str(body.direction or "WAIT").upper()
    source = _normalize_history_source(body.source or HISTORY_DEFAULT_SOURCE)
    if _autotrade_source_excluded(source):
        return {"saved": False, "reason": "MODULE_REMOVED"}
    interval = validate_interval(body.interval)
    symbol = clean_symbol(body.symbol)
    if direction not in {"BUY", "SELL"}:
        return {"saved": False, "reason": "WAIT"}

    try:
        live_candles, _, _ = await get_candles(symbol, interval, 260)
        entry, sl, tp, repaired = _normalize_auto_trade_levels({
            "entry": body.entry, "stop_loss": body.stop_loss, "take_profit": body.take_profit
        }, live_candles, direction, interval)
    except Exception as exc:
        return {"saved": False, "reason": f"LIVE_LEVELS_UNAVAILABLE: {exc}"}
    target_reached = not bool(tp)
    live_candle_time = _normalize_history_candle_time(live_candles[-1].get("time"))

    # Exactly one record per module/timeframe/live candle. Direction is mutable while
    # the current candle recalculates; do not create a second row on a BUY↔SELL flip.
    q = select(SignalHistory).where(
        SignalHistory.user_id == user.id,
        SignalHistory.source == source,
        SignalHistory.symbol == symbol,
        SignalHistory.interval == interval,
        SignalHistory.candle_time == live_candle_time
    ).order_by(SignalHistory.id.desc())
    existing = session.scalar(q)

    payload = dict(body.payload or {})
    setup_strength, setup_grade, strong_setup = _setup_strength_from_payload(payload, body.confidence)
    payload.update({
        "source": source, "symbol": symbol, "interval": interval, "confidence_at_entry": body.confidence,
        "setup": {"entry": entry, "stop_loss": sl, "take_profit": tp},
        "signal": {"direction": ("WAIT" if target_reached else direction), "original_direction": direction, "confidence": body.confidence},
        "target_state": "TARGET_REACHED" if target_reached else "ACTIVE", "candle_time": live_candle_time,
        "live_levels_verified": True, "levels_repaired_from_live_chart": bool(repaired),
        "setup_strength": setup_strength, "setup_grade": setup_grade, "strong_setup": strong_setup,
    })
    snapshot=_history_snapshot_payload(payload,source,symbol,interval,direction,body.confidence,entry,sl,tp,live_candle_time)
    payload["history_snapshot"]=snapshot
    history_direction = "WAIT" if target_reached else direction
    history_status = "CANCELLED" if target_reached else "ACTIVE"
    history_outcome = "TARGET_REACHED" if target_reached else "OPEN"
    row = SignalHistory(
        user_id=user.id, symbol=symbol, interval=interval, direction=history_direction, headline=(body.headline or f"{source} · {history_direction}")[:255],
        price=float(entry), payload=json.dumps(payload, ensure_ascii=False), outcome=history_outcome, status=history_status, created_at=datetime.now(timezone.utc), source=source, candle_time=live_candle_time
    )
    _history_sync_row(row,payload)
    if existing is None:
        try:
            session.add(row); session.commit(); session.refresh(row)
        except IntegrityError:
            session.rollback()
            existing = session.scalar(q)
            if existing is None:
                raise
    if existing is not None and str(existing.status or "ACTIVE").upper() in {"ACTIVE", "TP1 HIT", "OPEN"} and str(existing.outcome or "OPEN").upper() in {"OPEN", "TP1 HIT"}:
        existing.direction = direction
        existing.headline = (body.headline or f"{source} · {direction}")[:255]
        existing.price = float(entry)
        existing.payload = json.dumps(payload, ensure_ascii=False, default=str)
        existing.status = "ACTIVE" if str(existing.status or "ACTIVE").upper() != "TP1 HIT" else existing.status
        existing.outcome = "OPEN" if str(existing.outcome or "OPEN").upper() != "TP1 HIT" else existing.outcome
        _history_sync_row(existing, payload)
        session.commit()

    order = None
    rr_value = None
    try:
        risk_abs = abs(float(entry) - float(sl)) if sl is not None else 0
        rr_value = ((float(tp[0]) - float(entry)) / risk_abs) if direction == "BUY" and risk_abs > 0 else ((float(entry) - float(tp[0])) / risk_abs) if direction == "SELL" and risk_abs > 0 else None
    except Exception:
        rr_value = None
    if direction in {"BUY", "SELL"} and tp and not target_reached and rr_value is not None and rr_value >= 1.50:
        order = _queue_autotrade_order(
            symbol=symbol, source=source, interval=interval, direction=direction,
            entry=entry, sl=sl, tp=tp, volume=MT5_LOT_SIZE,
            confidence=body.confidence, candle_time=live_candle_time, risk_reward=rr_value,
        )
    if existing is not None:
        return {"saved": False, "updated": str(existing.status or "ACTIVE").upper() in {"ACTIVE", "TP1 HIT", "OPEN"}, "duplicate": True, "id": existing.id, "queued": bool(order),
                "source": source, "symbol": symbol, "entry": existing.price, "stop_loss": existing.stop_loss,
                "take_profit": [x for x in (existing.take_profit_1, existing.take_profit_2) if x is not None], "direction": existing.direction, "candle_time": live_candle_time}
    return {"saved": True, "id": row.id, "source": source, "outcome": row.outcome,
            "symbol": symbol, "entry": entry, "stop_loss": sl, "take_profit": tp,
            "candle_time": live_candle_time, "queued": bool(order)}

@app.get("/api/v1/signals/analytics")
async def signal_analytics(period: str = Query("all"), date: str | None = Query(None), symbol: str = Query(""), authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    user = current_user(authorization, session)
    requested_symbol = clean_symbol(symbol) if symbol else ""
    rows = await refresh_signal_outcomes(session, user.id, limit=500)
    if requested_symbol:
        rows = [r for r in rows if clean_symbol(r.symbol) == requested_symbol]
    rows = filter_history_rows(rows, period, date)
    wins = sum(1 for r in rows if _history_status(r) == "TP2 HIT" or r.outcome == "TP HIT")
    losses = sum(1 for r in rows if _history_status(r) == "SL HIT" or r.outcome == "SL HIT")
    completed = wins + losses
    winrate = round((wins / completed) * 100, 2) if completed else 0.0
    by_tf: dict[str, dict[str, Any]] = {}
    by_source: dict[str, dict[str, Any]] = {}
    by_date: dict[str, dict[str, Any]] = {}

    def bucket() -> dict[str, Any]:
        return {"total_signals":0,"completed_trades":0,"wins":0,"losses":0,"open":0,"ambiguous":0,"winrate":0.0}

    def finish(item: dict[str, Any]) -> None:
        item["completed_trades"] = item["wins"] + item["losses"]
        item["winrate"] = round(item["wins"] / item["completed_trades"] * 100, 2) if item["completed_trades"] else 0.0

    for r in rows:
        item = by_tf.setdefault(r.interval, bucket())
        src = getattr(r, "source", None) or HISTORY_DEFAULT_SOURCE
        src_item = by_source.setdefault(src, bucket())
        dt = r.created_at
        if dt is None:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        day_key = dt.astimezone(HISTORY_LOCAL_TZ).date().isoformat()
        day_item = by_date.setdefault(day_key, bucket())

        for target in (item, src_item, day_item):
            target["total_signals"] += 1
            status = _history_status(r)
            if status == "TP2 HIT" or r.outcome == "TP HIT":
                target["wins"] += 1
            elif status == "SL HIT" or r.outcome == "SL HIT":
                target["losses"] += 1
            elif status == "CANCELLED" or r.outcome == "AMBIGUOUS":
                target["ambiguous"] += 1
            elif status in {"ACTIVE", "TP1 HIT"} or r.outcome == "OPEN":
                target["open"] += 1
            finish(target)

    return {
        "total_signals": len(rows),
        "completed_trades": completed,
        "wins": wins,
        "losses": losses,
        "winrate": winrate,
        "open": sum(1 for r in rows if r.outcome == "OPEN"),
        "ambiguous": sum(1 for r in rows if r.outcome == "AMBIGUOUS"),
        "by_timeframe": by_tf,
        "by_source": by_source,
        "by_date": dict(sorted(by_date.items(), reverse=True)),
    }


# ---------------- Professional Signal History v2 ----------------
HISTORY_STATUS_VALUES = {"ACTIVE", "TP1 HIT", "TP2 HIT", "SL HIT", "EXPIRED", "CANCELLED", "TARGET_REACHED"}

def _history_snapshot_payload(payload: Any, source: str, symbol: str, interval: str, direction: str, confidence: Any = None,
                             entry: Any = None, sl: Any = None, tp: Any = None, candle_time: Any = None) -> dict[str, Any]:
    """Freeze the signal-time evidence in a JSON snapshot; never mutate it later."""
    base = payload if isinstance(payload, dict) else {"raw": payload}
    snap = json.loads(json.dumps(base, ensure_ascii=False, default=str))
    snap.setdefault("history_snapshot_version", "2.0")
    snap["source"] = source
    snap["symbol"] = clean_symbol(symbol)
    snap["interval"] = interval
    snap["direction"] = direction
    snap["confidence_at_entry"] = confidence
    snap["setup"] = {
        "entry": entry, "stop_loss": sl,
        "take_profit": list(tp or []) if isinstance(tp, (list, tuple)) else tp,
    }
    snap["candle_time"] = str(candle_time) if candle_time is not None else None
    snap["snapshot_created_at"] = datetime.now(timezone.utc).isoformat()
    snap["immutable"] = True
    return snap

def _history_numeric_levels(payload: dict[str, Any], row: SignalHistory) -> tuple[float | None, float | None, float | None, float | None]:
    setup = payload.get("setup") if isinstance(payload.get("setup"), dict) else {}
    adv = payload.get("advanced") if isinstance(payload.get("advanced"), dict) else (payload.get("signal") if isinstance(payload.get("signal"), dict) else {})
    module = payload.get("module_signal") if isinstance(payload.get("module_signal"), dict) else {}
    entry = setup.get("entry", payload.get("entry", adv.get("entry", module.get("entry", row.price))))
    sl = setup.get("stop_loss", payload.get("stop_loss", payload.get("sl", adv.get("stop_loss", module.get("stop_loss")))))
    tps = setup.get("take_profit", payload.get("take_profit", payload.get("tp", adv.get("take_profit", module.get("take_profit", [])))))
    def f(v):
        try: return float(v) if v is not None else None
        except Exception: return None
    tp1 = f(tps[0]) if isinstance(tps, (list, tuple)) and len(tps) > 0 else f(tps)
    tp2 = f(tps[1]) if isinstance(tps, (list, tuple)) and len(tps) > 1 else None
    return f(entry), f(sl), tp1, tp2

def _history_score_strength(payload: dict[str, Any]) -> tuple[float | None, str | None, float | None]:
    score = payload.get("signal_score", payload.get("score", payload.get("confidence_at_entry", payload.get("confidence"))))
    try: score = float(score) if score is not None else None
    except Exception: score = None
    strength = payload.get("signal_strength") or payload.get("setup_grade") or payload.get("strength")
    rr = payload.get("risk_reward") or payload.get("rr")
    try: rr = float(rr) if rr is not None else None
    except Exception: rr = None
    return score, str(strength) if strength is not None else None, rr

def _history_sync_row(row: SignalHistory, payload: dict[str, Any]) -> None:
    entry, sl, tp1, tp2 = _history_numeric_levels(payload, row)
    score, strength, rr = _history_score_strength(payload)
    row.entry_price, row.stop_loss, row.take_profit_1, row.take_profit_2 = entry, sl, tp1, tp2
    row.signal_score, row.signal_strength, row.risk_reward = score, strength, rr
    row.status = row.status or ("ACTIVE" if row.outcome in {None, "OPEN"} else row.outcome)
    row.result = row.result or (row.outcome if row.outcome not in {None, "OPEN", "AMBIGUOUS"} else None)
    if not row.signal_uid:
        row.signal_uid = "SIG-" + secrets.token_hex(10).upper()

def _history_result_metrics(row: SignalHistory, status: str, result_price: float | None) -> tuple[float | None, float | None]:
    entry, sl = row.entry_price, row.stop_loss
    if entry is None or sl is None or entry == sl or result_price is None: return None, None
    risk = abs(entry - sl)
    pnl = (result_price - entry) if row.direction == "BUY" else (entry - result_price)
    return round(pnl, 4), round(pnl / risk, 4) if risk else None


def _history_status(row: SignalHistory) -> str:
    s = (getattr(row, "status", None) or "").upper().strip()
    if s == "OPEN": return "ACTIVE"
    if s == "TP HIT": return "TP2 HIT"
    if s == "AMBIGUOUS": return "CANCELLED"
    if s == "TARGET_REACHED": return "TARGET_REACHED"
    return s or ("ACTIVE" if row.outcome == "OPEN" else row.outcome or "ACTIVE")

def _history_v2_date_bounds(start_date: str | None, end_date: str | None):
    """Convert UI dates in Asia/Tashkent into UTC [start, end) bounds."""
    start_dt = end_dt = None
    tz = HISTORY_LOCAL_TZ
    if start_date:
        try:
            d = datetime.strptime(start_date, "%Y-%m-%d").date()
            start_dt = datetime(d.year, d.month, d.day, tzinfo=tz).astimezone(timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail="start_date YYYY-MM-DD formatda bo‘lishi kerak")
    if end_date:
        try:
            d = datetime.strptime(end_date, "%Y-%m-%d").date()
            next_d = d + timedelta(days=1)
            end_dt = datetime(next_d.year, next_d.month, next_d.day, tzinfo=tz).astimezone(timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail="end_date YYYY-MM-DD formatda bo‘lishi kerak")
    if start_dt and end_dt and start_dt >= end_dt:
        raise HTTPException(status_code=400, detail="start_date end_date dan katta yoki teng bo‘lishi mumkin emas")
    return start_dt, end_dt

# History outcome refresh is throttled so opening the journal repeatedly does not
# trigger repeated candle scans. It does not alter signal generation or execution.
_HISTORY_V2_REFRESH_TS: dict[int, float] = {}
_HISTORY_V2_REFRESH_LOCKS: dict[int, asyncio.Lock] = {}
_HISTORY_V2_REFRESH_COOLDOWN = max(5.0, float(os.getenv("HISTORY_V2_REFRESH_COOLDOWN", "20")))

async def _maybe_refresh_history_v2(session: Session, user_id: int, limit: int = 2000) -> None:
    uid = int(user_id)
    lock = _HISTORY_V2_REFRESH_LOCKS.setdefault(uid, asyncio.Lock())
    async with lock:
        now_mono = asyncio.get_running_loop().time()
        last = _HISTORY_V2_REFRESH_TS.get(uid, 0.0)
        if now_mono - last < _HISTORY_V2_REFRESH_COOLDOWN:
            return
        try:
            await refresh_signal_outcomes(session, uid, limit=limit)
        except Exception as exc:
            # Outcome refresh is best-effort; History reads must not become HTTP 500.
            print(f"[HISTORY V2] outcome refresh skipped: {type(exc).__name__}: {exc}")
        finally:
            _HISTORY_V2_REFRESH_TS[uid] = asyncio.get_running_loop().time()

@app.get("/api/v2/signal-history")
async def signal_history_v2(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                            start_date: str | None = Query(None), end_date: str | None = Query(None),
                            symbol: str = Query(""), direction: str = Query(""), result: str = Query(""),
                            module: str = Query(""), authorization: str | None = Header(default=None),
                            session: Session = Depends(db)) -> dict[str, Any]:
    user = current_user(authorization, session)
    try:
        await _maybe_refresh_history_v2(session, user.id)
    except Exception as exc:
        print(f"[HISTORY V2] outcome refresh skipped: {type(exc).__name__}: {exc}")
    q = select(SignalHistory).where(SignalHistory.user_id == user.id, ~SignalHistory.source.in_(LEGACY_EXCLUDED_SIGNAL_SOURCES))
    if symbol:
        q = q.where(SignalHistory.symbol == clean_symbol(symbol))
    if direction and direction.upper() in {"BUY", "SELL"}:
        q = q.where(SignalHistory.direction == direction.upper())
    if result:
        norm = result.upper().replace("_", " ")
        q = q.where((SignalHistory.status == norm) | (SignalHistory.outcome == norm))
    if module:
        q = q.where(SignalHistory.source == module)
    start_dt, end_dt = _history_v2_date_bounds(start_date, end_date)
    if start_dt is not None:
        q = q.where(SignalHistory.created_at >= start_dt)
    if end_dt is not None:
        q = q.where(SignalHistory.created_at < end_dt)
    total_count = int(session.scalar(select(func.count()).select_from(q.subquery())) or 0)
    rows = list(session.scalars(q.order_by(SignalHistory.created_at.desc(), SignalHistory.id.desc()).offset(offset).limit(limit)).all())
    items=[]
    for r in rows:
        try: payload=json.loads(r.payload or "{}")
        except Exception: payload={}
        if not isinstance(payload, dict):
            payload = {"raw_payload": payload}
        _history_sync_row(r,payload)
        entry,sl,tp1,tp2=r.entry_price,r.stop_loss,r.take_profit_1,r.take_profit_2
        dt=r.created_at or datetime.now(timezone.utc)
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        closed=r.closed_at if r.closed_at and r.closed_at.tzinfo else (r.closed_at.replace(tzinfo=timezone.utc) if r.closed_at else None)
        duration=round(max(0,(closed-dt).total_seconds())/60,2) if closed else None
        status=_history_status(r)
        snap=payload.get("history_snapshot") if isinstance(payload.get("history_snapshot"),dict) else payload
        items.append({"id":r.id,"signal_id":r.signal_uid,"symbol":r.symbol,"direction":r.direction,"score":r.signal_score,"strength":r.signal_strength,
                      "entry":entry,"sl":sl,"tp1":tp1,"tp2":tp2,"rr":r.risk_reward,"created_at":dt.isoformat(),"closed_at":closed.isoformat() if closed else None,
                      "duration_minutes":duration,"status":status,"result":r.result or (status if status in {"TP2 HIT","SL HIT"} else None),
                      "profit_loss":r.profit_loss,"r_multiple":r.r_multiple,"result_price":(payload.get("result", {}).get("price") if isinstance(payload.get("result"), dict) else None),"source":r.source or HISTORY_DEFAULT_SOURCE,"interval":r.interval,"candle_time":r.candle_time,
                      "auto_entry":bool(payload.get("auto_entry")),"snapshot":snap})
    return {"ok":True,"timezone":"Asia/Tashkent","items":items,"count":len(items),"total_count":total_count,"offset":offset,"limit":limit}

@app.post("/api/v2/signal-history/refresh")
async def signal_history_refresh_v2(authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    user = current_user(authorization, session)
    try:
        await refresh_signal_outcomes(session, user.id, limit=2000)
        rows = list(session.scalars(select(SignalHistory).where(
            SignalHistory.user_id == user.id,
            ~SignalHistory.source.in_(LEGACY_EXCLUDED_SIGNAL_SOURCES)
        )).all())
        counts = {"active": 0, "tp1": 0, "wins": 0, "losses": 0, "target_reached": 0, "cancelled": 0}
        for r in rows:
            st = _history_status(r)
            if st == "ACTIVE": counts["active"] += 1
            elif st == "TP1 HIT": counts["tp1"] += 1
            elif st == "TP2 HIT": counts["wins"] += 1
            elif st == "SL HIT": counts["losses"] += 1
            elif st == "TARGET_REACHED": counts["target_reached"] += 1
            elif st in {"CANCELLED", "EXPIRED"}: counts["cancelled"] += 1
        return {"ok": True, "refreshed": len(rows), "counts": counts, "timezone": "Asia/Tashkent"}
    except Exception as exc:
        try: session.rollback()
        except Exception: pass
        print(f"[HISTORY REFRESH ENDPOINT] warning={type(exc).__name__}: {exc}")
        return {"ok": True, "refreshed": 0, "warning": "Outcome refresh vaqtincha mavjud emas.", "timezone": "Asia/Tashkent"}

@app.get("/api/v2/signal-history/stats")
async def signal_history_stats_v2(start_date: str | None = Query(None), end_date: str | None = Query(None), symbol: str = Query(""),
                                  direction: str = Query(""), result: str = Query(""), module: str = Query(""),
                                  authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    user=current_user(authorization,session)
    try:
        await _maybe_refresh_history_v2(session, user.id)
    except Exception as exc:
        print(f"[HISTORY V2 STATS] outcome refresh skipped: {type(exc).__name__}: {exc}")
    q=select(SignalHistory).where(SignalHistory.user_id==user.id, ~SignalHistory.source.in_(LEGACY_EXCLUDED_SIGNAL_SOURCES))
    if symbol: q=q.where(SignalHistory.symbol==clean_symbol(symbol))
    if direction.upper() in {"BUY","SELL"}: q=q.where(SignalHistory.direction==direction.upper())
    if module: q=q.where(SignalHistory.source==module)
    rows=list(session.scalars(q.order_by(SignalHistory.created_at.desc())).all())
    def date_ok(r):
        dt=r.created_at
        if dt is None: return False
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        d=dt.astimezone(HISTORY_LOCAL_TZ).date()
        try:
            if start_date and d<datetime.strptime(start_date,"%Y-%m-%d").date(): return False
            if end_date and d>datetime.strptime(end_date,"%Y-%m-%d").date(): return False
        except ValueError: return False
        return True
    def st(r): return _history_status(r)
    rows=[r for r in rows if date_ok(r)]
    if result:
        rr=result.upper().replace("_"," ")
        rows=[r for r in rows if st(r)==rr or (r.outcome or "").upper()==rr]
    def bucket(): return {"signals":0,"wins":0,"losses":0,"active":0,"tp1":0,"tp2":0,"total_r":0.0,"total_profit":0.0,"avg_rr":0.0,"winrate":0.0}
    overall=bucket(); by_module={}; by_day={}; by_symbol={}; by_direction={}
    for r in rows:
        s=st(r); k=(r.source or HISTORY_DEFAULT_SOURCE)
        dt=r.created_at
        if dt is None:
            continue
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        day=dt.astimezone(HISTORY_LOCAL_TZ).date().isoformat()
        targets=[overall, by_module.setdefault(k,bucket()), by_day.setdefault(day,bucket()), by_symbol.setdefault(r.symbol,bucket()), by_direction.setdefault(r.direction,bucket())]
        for b in targets:
            b["signals"]+=1
            if s=="TP2 HIT": b["wins"]+=1
            elif s=="SL HIT": b["losses"]+=1
            elif s=="ACTIVE": b["active"]+=1
            elif s=="TP1 HIT": b["tp1"]+=1
            b["total_r"] += float(r.r_multiple or 0)
            b["total_profit"] += float(r.profit_loss or 0)
            if r.risk_reward: b["avg_rr"] += float(r.risk_reward)
    for b in [overall,*by_module.values(),*by_day.values(),*by_symbol.values(),*by_direction.values()]:
        finished=b["wins"]+b["losses"]
        b["winrate"]=round(b["wins"]/finished*100,2) if finished else 0.0
        b["avg_rr"]=round(b["avg_rr"]/b["signals"],2) if b["signals"] else 0.0
        b["total_r"]=round(b["total_r"],2); b["total_profit"]=round(b["total_profit"],2)
    return {"ok":True,"timezone":"Asia/Tashkent","overall":overall,"by_module":by_module,"by_day":dict(sorted(by_day.items(),reverse=True)),"by_symbol":by_symbol,"by_direction":by_direction}

@app.get("/api/v1/signals/history")
async def signal_history(limit: int = Query(50, ge=1, le=200), period: str = Query("all"), date: str | None = Query(None), symbol: str = Query(""), authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    user = current_user(authorization, session)
    requested_symbol = clean_symbol(symbol) if symbol else ""
    # Always isolate history by the currently requested trading symbol.
    # History reads must stay fast and must never trigger expensive TradingView outcome scans.
    # Outcomes are refreshed by the auto-record/background path; this endpoint is read-only.
    if requested_symbol:
        rows = list(session.scalars(select(SignalHistory).where(SignalHistory.user_id == user.id, ~SignalHistory.source.in_(LEGACY_EXCLUDED_SIGNAL_SOURCES), SignalHistory.symbol == requested_symbol).order_by(SignalHistory.created_at.desc()).limit(limit)))
        rows = list(reversed(rows))
    else:
        rows = list(session.scalars(select(SignalHistory).where(SignalHistory.user_id == user.id, ~SignalHistory.source.in_(LEGACY_EXCLUDED_SIGNAL_SOURCES)).order_by(SignalHistory.created_at.desc()).limit(limit)))
        rows = list(reversed(rows))
    rows = filter_history_rows(rows, period, date)
    rows = rows[-limit:][::-1]
    items = []
    for r in rows:
        payload = {}
        try: payload = json.loads(r.payload)
        except Exception: pass
        setup = payload.get("setup") if isinstance(payload.get("setup"), dict) else {}
        # Current auto-trade records keep execution levels at the payload root;
        # legacy records use setup/advanced; module history records use module_signal.
        module_signal = payload.get("module_signal") if isinstance(payload.get("module_signal"), dict) else {}
        adv = payload.get("advanced") if isinstance(payload.get("advanced"), dict) else (payload.get("signal") if isinstance(payload.get("signal"), dict) else {})
        setup = {
            "entry": setup.get("entry", adv.get("entry", module_signal.get("entry", payload.get("entry", r.price)))),
            "stop_loss": setup.get("stop_loss", adv.get("stop_loss", module_signal.get("stop_loss", payload.get("stop_loss", payload.get("sl"))))),
            "take_profit": setup.get("take_profit", adv.get("take_profit", module_signal.get("take_profit", payload.get("take_profit", payload.get("tp", []))))),
        }
        raw_result = payload.get("result")
        # Legacy rows sometimes stored result as a string; never assume dict.
        result = raw_result if isinstance(raw_result, dict) else {}
        created_at = r.created_at
        if created_at is None:
            created_at = datetime.now(timezone.utc)
        elif created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        closed_at = r.closed_at
        if closed_at and closed_at.tzinfo is None:
            closed_at = closed_at.replace(tzinfo=timezone.utc)
        duration_seconds = result.get("duration_seconds")
        if duration_seconds is None and closed_at:
            duration_seconds = max(0, int((closed_at - created_at).total_seconds()))
        setup_strength, setup_grade, strong_setup = _setup_strength_from_payload(payload, payload.get("confidence_at_entry", ((payload.get("signal") or {}).get("confidence") if isinstance(payload.get("signal"), dict) else None)))
        entry_value = setup.get("entry", r.price)
        tp_value = setup.get("take_profit", [])
        sl_value = setup.get("stop_loss")
        tp_pips, tp_pips_total, sl_pips = history_level_pips(r.symbol, entry_value, tp_value, sl_value)
        items.append({"id": r.id, "symbol": r.symbol, "interval": r.interval, "source": getattr(r, "source", None) or HISTORY_DEFAULT_SOURCE, "candle_time": getattr(r, "candle_time", None), "direction": r.direction, "entry": entry_value, "tp": tp_value, "sl": sl_value, "tp_pips": tp_pips, "tp_pips_total": tp_pips_total, "sl_pips": sl_pips, "pip_size": history_pip_size(r.symbol), "headline": r.headline, "price": r.price, "outcome": r.outcome, "result_price": result.get("price"), "duration_seconds": duration_seconds, "duration_minutes": round(duration_seconds/60,2) if duration_seconds is not None else None, "auto_entry": bool(payload.get("auto_entry")), "confidence": payload.get("confidence_at_entry", ((payload.get("signal") or {}).get("confidence") if isinstance(payload.get("signal"), dict) else None)), "setup_strength": payload.get("setup_strength", setup_strength), "setup_grade": payload.get("setup_grade", setup_grade), "strong_setup": bool(payload.get("strong_setup", strong_setup)), "created_at": created_at.isoformat(), "closed_at": closed_at.isoformat() if closed_at else None})
    return {"items": items}


class AIControlBody(BaseModel):
    provider: str | None = None
    enabled: bool | None = None
    all_enabled: bool | None = None

@app.post("/api/v1/ai/providers/control")
async def ai_providers_control(body: AIControlBody, authorization: str | None = Header(default=None), session: Session = Depends(db)):
    require_admin(authorization, session)
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

@app.get("/api/v1/market/providers")
async def get_market_providers() -> dict[str, Any]:
    now_mono = asyncio.get_running_loop().time()
    rows = []
    for provider in _market_provider_order():
        status = dict(MARKET_PROVIDER_STATUS.get(provider, {}))
        cooldown = MARKET_PROVIDER_COOLDOWN_UNTIL.get(provider, 0.0)
        status["id"] = provider
        status["name"] = _market_provider_name(provider)
        status["enabled"] = _market_provider_enabled(provider)
        status["cooldown_seconds_remaining"] = max(0, int(cooldown - now_mono))
        rows.append(status)
    return {"ok": True, "preferred": MARKET_PROVIDER or "auto", "order": MARKET_FALLBACK_ORDER, "providers": rows}


@app.get("/api/v1/ai/providers")
async def ai_providers_status(authorization: str | None = Header(default=None), session: Session = Depends(db)):
    require_admin(authorization, session)
    # Only configured providers are exposed to the dashboard. Missing-key
    # providers are intentionally hidden instead of showing "OFFLINE".
    configured={
        "groq": bool(GROQ_API_KEY),
        "groq_2": bool(GROQ_API_KEY_2),
        "gemini": bool(GEMINI_API_KEY),
        "anthropic": bool(ANTHROPIC_API_KEY),
        "anthropic_2": bool(ANTHROPIC_API_KEY),
        "anthropic_3": bool(ANTHROPIC_API_KEY),
        "openrouter": bool(OPENROUTER_API_KEY),
        "mistral": bool(MISTRAL_API_KEY),
        "cerebras": bool(CEREBRAS_API_KEY),
        "cloudflare": bool(CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN),
        "deepseek": bool(DEEPSEEK_API_KEY),
        "openai": bool(OPENAI_API_KEY),
        "huggingface": bool(HF_TOKEN),
    }
    models={"groq":GROQ_MODEL,"groq_2":GROQ_MODEL_2,"gemini":GEMINI_MODEL,"anthropic":ANTHROPIC_MODEL,"anthropic_2":ANTHROPIC_MODEL_2,"anthropic_3":ANTHROPIC_MODEL_3,"openrouter":OPENROUTER_MODEL,"mistral":MISTRAL_MODEL,"cerebras":CEREBRAS_MODEL,"cloudflare":CLOUDFLARE_MODEL,"deepseek":DEEPSEEK_MODEL,"openai":OPENAI_MODEL,"huggingface":HF_MODEL}
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
    return {
        "order":[x["id"] for x in providers],
        "router": AI_ROUTER_MODE,
        "preferred": None if AI_PROVIDER in {"auto", ""} else AI_PROVIDER,
        "automatic_failover": True,
        "free_first": True,
        "paid_fallback_enabled": AI_PAID_FALLBACK_ENABLED,
        "paid_fallback_order":[p for p in AI_FALLBACK_ORDER if p in AI_PAID_PROVIDER_IDS],
        "providers": providers,
    }

@app.get("/api/v1/mt5/status")
async def mt5_status(symbol: str = DEFAULT_SYMBOL, authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    require_admin(authorization, session)
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
    return {"ok": True, "symbol": key, "auto_trading": MT5_AUTO_TRADING if key == "XAU/USD" else False, "lot": MT5_LOT_SIZE, "state": state, "queue": len(MT5_ORDER_QUEUE), "demo_only": True, "heartbeat_timeout_sec": MT5_HEARTBEAT_TIMEOUT}

@app.post("/api/v1/mt5/connect")
async def mt5_connect(body: MT5ConnectBody, authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    require_admin(authorization, session)
    if not body.demo:
        raise HTTPException(status_code=400, detail="Faqat DEMO hisob ulanishi mumkin.")
    if not body.login or not body.server or not body.password:
        raise HTTPException(status_code=400, detail="MT5 Login, Server va Trading Password kiriting.")
    # Credentials are intentionally NOT persisted. The actual broker login is performed by MT5 terminal/EA.
    MT5_BRIDGE_STATE.update({"login": body.login, "server": body.server, "connected": False, "last_error": "MT5 terminal/EA bridge hali ulanmagan."})
    return {"ok": True, "demo_only": True, "connected": False, "message": "Ma'lumotlar qabul qilindi. Exness DEMO MT5 terminalida EA/bridge ishga tushirilgach ulanish tasdiqlanadi."}

@app.post("/api/v1/mt5/lot")
async def mt5_lot(body: MT5LotBody, authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    require_admin(authorization, session)
    global MT5_LOT_SIZE
    lot = float(body.lot)
    if not (0.01 <= lot <= 100.0):
        raise HTTPException(status_code=400, detail="Lot 0.01 dan 100 gacha bo‘lishi kerak.")
    # Normalize to two decimals for common MT5 lot steps.
    MT5_LOT_SIZE = round(lot, 2)
    return {"ok": True, "lot": MT5_LOT_SIZE, "demo_only": True}

@app.post("/api/v1/mt5/auto-trading")
async def mt5_auto_trading(enabled: bool = Query(...), authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    require_admin(authorization, session)
    global MT5_AUTO_TRADING
    MT5_AUTO_TRADING = bool(enabled)
    return {"ok": True, "auto_trading": MT5_AUTO_TRADING, "demo_only": True}


@app.get("/api/v1/mt5/poll")
async def mt5_poll(token: str = Query(...), market: str = Query(...), client_id: str = Query("")) -> dict[str, Any]:
    """Return ONLY orders for the requested canonical market.

    The bridge is XAU/USD-only. This is a hard transport boundary.
    """
    if not secrets.compare_digest(token, MT5_BRIDGE_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid MT5 bridge token")
    requested_market = _mt5_market_key(market)
    if requested_market != "XAU/USD":
        raise HTTPException(status_code=400, detail="Unsupported MT5 market: only XAU/USD is enabled")
    MT5_BRIDGE_STATE["last_seen"] = datetime.now(timezone.utc).isoformat()
    now = datetime.now(timezone.utc).timestamp()
    client = re.sub(r"[^A-Za-z0-9._:-]+", "_", str(client_id or "").strip())[:100]
    if not client:
        client = "legacy"
    # Expire dead-client leases so a crashed terminal cannot permanently hold an order.
    for item in MT5_ORDER_QUEUE:
        if item.get("claimed") and float(item.get("claim_expires", 0) or 0) <= now:
            item["claimed"] = False
            item.pop("claimed_by", None)
            item.pop("claim_expires", None)
    if not MT5_AUTO_TRADING or not MT5_ORDER_QUEUE:
        return {"ok": True, "market": requested_market, "orders": [], "client_id": client}
    MT5_BRIDGE_CLIENTS[client] = {"last_seen": now, "market": requested_market}
    # Claim a small batch for THIS market and THIS bridge client. A second terminal
    # using the same token cannot take an active lease away from the first one.
    orders = []
    for item in MT5_ORDER_QUEUE:
        if item.get("claimed"):
            continue
        item_market = _mt5_market_key(item.get("market") or item.get("symbol"))
        if item_market != requested_market:
            continue
        if str(item.get("interval") or "").strip().lower() in {"1min", "1m", "m1"}:
            print(f"[MT5 POLL] M1 ORDER BLOCKED id={item.get('id')} market={item_market}")
            continue
        item["claimed"] = True
        item["claimed_by"] = client
        item["claim_expires"] = now + MT5_CLAIM_LEASE_SECONDS
        MT5_ORDER_ATTEMPTS[item["id"]] = MT5_ORDER_ATTEMPTS.get(item["id"], 0) + 1
        orders.append(item)
        if len(orders) >= 10:
            break
    return {"ok": True, "market": requested_market, "orders": orders, "client_id": client, "lease_seconds": MT5_CLAIM_LEASE_SECONDS}

@app.post("/api/v1/mt5/state")
async def mt5_state(body: MT5StateBody, token: str = Query(...)) -> dict[str, Any]:
    if not secrets.compare_digest(token, MT5_BRIDGE_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid MT5 bridge token")
    now_iso = datetime.now(timezone.utc).isoformat()
    markets_payload = body.markets or {}
    if markets_payload:
        saved = []
        for raw_key, raw_market in markets_payload.items():
            key = _mt5_market_key(raw_key)
            if not isinstance(raw_market, dict):
                continue
            snapshot = {
                "connected": bool(raw_market.get("connected", body.connected)),
                "account": raw_market.get("account") or body.login or None,
                "server": raw_market.get("server") or body.server or None,
                "balance": raw_market.get("balance", body.balance),
                "equity": raw_market.get("equity", body.equity),
                "free_margin": raw_market.get("free_margin", body.free_margin),
                "margin": raw_market.get("margin", body.margin),
                "positions": raw_market.get("positions", body.positions),
                "last_seen": now_iso,
                "last_error": raw_market.get("error") or body.error or "",
                "symbol": key,
                "candles": raw_market.get("candles") or {},
            }
            MT5_BRIDGE_STATE.setdefault("markets", {})[key] = snapshot
            saved.append(key)
        # Keep global heartbeat fresh while preserving the per-symbol snapshots.
        MT5_BRIDGE_STATE.update({"connected": bool(body.connected), "login": body.login or None, "server": body.server or None, "last_seen": now_iso, "last_error": body.error or "", "symbol": saved[0] if saved else body.symbol or None})
        return {"ok": True, "symbols": saved}
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
    report_client = re.sub(r"[^A-Za-z0-9._:-]+", "_", str(body.client_id or "").strip())[:100]
    if report_client:
        MT5_BRIDGE_CLIENTS.setdefault(report_client, {})["last_seen"] = datetime.now(timezone.utc).timestamp()
    status = body.status.lower()
    if status in {"error", "failed", "order_failed"}:
        MT5_BRIDGE_STATE["last_error"] = body.message
    # Finalize a claimed queue item using the EA's order id. Successful orders are
    # removed; failed orders are released for a limited retry count.
    if body.ticket:
        for idx, item in enumerate(list(MT5_ORDER_QUEUE)):
            if str(item.get("id")) != str(body.ticket):
                continue
            claimed_by = str(item.get("claimed_by") or "")
            report_client = re.sub(r"[^A-Za-z0-9._:-]+", "_", str(body.client_id or "").strip())[:100]
            if claimed_by and report_client and claimed_by != report_client:
                break
            if status in {"order_sent", "sent", "success", "filled"}:
                qk = item.get("queue_key")
                if isinstance(qk, list) and len(qk) == 5:
                    MT5_EXECUTED_KEYS.add(tuple(str(x) for x in qk))
                MT5_ORDER_QUEUE.pop(idx)
                MT5_ORDER_ATTEMPTS.pop(str(body.ticket), None)
            elif status in {"error", "failed", "order_failed"}:
                attempts = MT5_ORDER_ATTEMPTS.get(str(body.ticket), 1)
                if attempts >= 3:
                    MT5_ORDER_QUEUE.pop(idx)
                    MT5_ORDER_ATTEMPTS.pop(str(body.ticket), None)
                else:
                    item["claimed"] = False
                    item.pop("claimed_by", None)
                    item.pop("claim_expires", None)
            break
    return {"ok": True, "queue": len(MT5_ORDER_QUEUE)}

# Runtime static/diagnostic fix: serve root-level CSS files and expose deployment diagnostics.
@app.get("/signalx-master-clean.css")
async def signalx_master_clean_css() -> FileResponse:
    return FileResponse(os.path.join(BASE_DIR, "signalx-master-clean.css"), media_type="text/css")

@app.get("/signalx-premium-theme.css")
async def signalx_premium_theme_css() -> FileResponse:
    return FileResponse(os.path.join(BASE_DIR, "signalx-premium-theme.css"), media_type="text/css")

@app.get("/api/deploy-diagnostics")
async def deploy_diagnostics(authorization: str | None = Header(default=None), session: Session = Depends(db)) -> dict[str, Any]:
    # Deployment fingerprints can help the owner debug production, but must not be public.
    require_admin(authorization, session)
    files = {}
    for name in ("index.html", "signalx-master-clean.css", "signalx-premium-theme.css", "app.js", "main.py"):
        path = os.path.join(BASE_DIR, name)
        exists = os.path.isfile(path)
        data = b""
        if exists:
            try:
                data = open(path, "rb").read()
            except Exception:
                data = b""
        files[name] = {"exists": exists, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest() if data else None}
    return {
        "ok": True,
        "diagnostic": "SIGNALX_RUNTIME_DIAGNOSTIC_V1",
        "server_time": datetime.now(timezone.utc).isoformat(),
        "base_dir": BASE_DIR,
        "files": files,
        "cwd": os.getcwd(),
    }

@app.get("/api/health")
async def api_health() -> dict[str, Any]:
    return {"ok": True, "service": "xauusd-trading", "timestamp": datetime.now(timezone.utc).isoformat()}

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


# --- SignalX additive MT5 Multi-Broker Account Gateway ---
# Keep Railway startup on `main:app`; the gateway is registered directly here
# after all core models/routes exist, so no replacement launcher is required.
from mt5_account_gateway import initialize_gateway_tables as _initialize_gateway_tables
from mt5_account_gateway import router as _mt5_gateway_router

_initialize_gateway_tables()
app.include_router(_mt5_gateway_router)
