# AI 24/7 Optimizer

- AI result cache is keyed by symbol + timeframe + candle_time and kept for the candle lifetime.
- Repeated requests on the same candle reuse the cached result.
- Providers are tried in `AI_FALLBACK_ORDER`.
- HTTP 429/rate-limit/quota responses put a provider into a short cooldown and the router immediately advances to the next provider.
- Providers are not considered configured unless their required environment variables exist.
- OpenAI-compatible providers retry once without `response_format=json_object` when a model rejects structured-output parameters.
- The deterministic trading engine remains available if all AI providers fail.

Recommended Railway variables:
- `AI_PROVIDER=auto`
- `AI_FALLBACK_ORDER=groq,gemini,openrouter,groq_qwen,mistral,cerebras,cloudflare,huggingface,openai`
- `AI_CACHE_TTL=86400`
- `AI_PROVIDER_COOLDOWN_SECONDS=120`
