# SignalX — Free-First AI Router

This build uses a **FREE-FIRST / PAID-LAST** routing policy for AI validation.

## Default order

1. Groq GPT-OSS 120B
2. Groq Qwen
3. Google Gemini Flash
4. Cerebras
5. Mistral
6. Cloudflare Workers AI
7. Hugging Face
8. OpenRouter Free
9. DeepSeek Flash — emergency low-cost paid fallback
10. Claude models — only if configured and needed
11. OpenAI — only if configured and needed

The router now uses `AI_ROUTER_MODE=order` by default, so a healthy free provider is tried before the next provider. Paid providers are reached only after the preceding configured free/low-cost providers fail, rate-limit, or are in cooldown.

## Railway variables

```text
AI_PROVIDER=auto
AI_ROUTER_MODE=order
AI_PAID_FALLBACK_ENABLED=true
AI_FALLBACK_ORDER=groq,groq_2,gemini,cerebras,mistral,cloudflare,huggingface,openrouter,deepseek,anthropic,anthropic_2,anthropic_3,openai
AI_CACHE_TTL=86400
AI_FAILURE_CACHE_TTL=20
AI_PROVIDER_COOLDOWN_SECONDS=120
```

For the current DeepSeek API, use:

```text
DEEPSEEK_API_KEY=...
DEEPSEEK_MODEL=deepseek-flash
```

Do not put API keys in GitHub. Keep them in Railway Variables/Secrets.

## 24/7 cost behavior

The important point is that the site being online for 24 hours does **not** mean 24 hours of AI billing. AI usage is generated only when SignalX sends an AI request.

The existing candle-level cache is preserved. Repeated requests on the same symbol/timeframe/candle reuse the cached AI result, so the router does not intentionally multiply AI calls on the same closed candle.

If all configured providers fail, SignalX keeps the deterministic trading engines available instead of blocking the dashboard.
