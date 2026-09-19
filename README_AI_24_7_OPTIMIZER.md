# AI 24/7 Optimizer

- AI result cache is keyed by symbol + timeframe + candle_time and kept for the candle lifetime.
- Repeated requests on the same candle reuse the cached result.
- Providers are tried in `AI_FALLBACK_ORDER`; the default is now **free-first, paid-last** with `AI_ROUTER_MODE=order`.
- HTTP 429/rate-limit/quota responses put a provider into a short cooldown and the router immediately advances to the next provider.
- Providers are not considered configured unless their required environment variables exist.
- OpenAI-compatible providers retry once without `response_format=json_object` when a model rejects structured-output parameters.
- The deterministic trading engine remains available if all AI providers fail.

Recommended Railway variables:
- `AI_PROVIDER=auto`
- `AI_FALLBACK_ORDER=groq,groq_2,gemini,cerebras,mistral,cloudflare,huggingface,openrouter,deepseek,anthropic,anthropic_2,anthropic_3,openai`
- `AI_CACHE_TTL=86400`
- `AI_ROUTER_MODE=order`
- `AI_PAID_FALLBACK_ENABLED=true`
- `AI_PROVIDER_COOLDOWN_SECONDS=120`

- Paid providers are only an emergency layer; set `AI_PAID_FALLBACK_ENABLED=false` to disable them completely.
