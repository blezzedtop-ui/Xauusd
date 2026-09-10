# Multi-AI Fallback Network

The trading site now uses a provider failover router. It never fetches market data itself: TradingView-derived candles and the deterministic Quant/ICT/SNR/Classic analysis are passed into the AI validator.

## Provider order
1. Groq GPT-OSS 120B
2. Google Gemini Flash
3. OpenRouter Free (`openrouter/free`)
4. Groq Qwen 3.6 27B
5. Mistral
6. Cerebras
7. Cloudflare Workers AI
8. Hugging Face Inference Providers
9. OpenAI (optional final fallback)

If a provider returns a timeout, HTTP error, 429/rate-limit, empty response, or is not configured, the router advances to the next configured provider. If all providers fail, the deterministic trading engine remains active.

## Railway variables

Required for the primary free path:

- `AI_PROVIDER=auto`
- `GROQ_API_KEY=...`
- `GROQ_MODEL=openai/gpt-oss-120b`

Optional backups:

- `GEMINI_API_KEY`, `GEMINI_MODEL=gemini-3.8-flash`
- `OPENROUTER_API_KEY`, `OPENROUTER_MODEL=openrouter/free`
- `GROQ_QWEN_MODEL=qwen/qwen3.6-27b` (uses the same Groq key)
- `MISTRAL_API_KEY`, `MISTRAL_MODEL=mistral-small-latest`
- `CEREBRAS_API_KEY`, `CEREBRAS_MODEL=gpt-oss-120b`
- `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_MODEL=@cf/meta/llama-3.1-8b-instruct`
- `HF_TOKEN`, `HF_MODEL=openai/gpt-oss-120b:fastest`
- `OPENAI_API_KEY`, `OPENAI_MODEL=gpt-5.6-sol`

The dashboard exposes `GET /api/v1/ai/providers` and shows each provider as ONLINE, READY, LIMITED, OFFLINE, or NOT_CONFIGURED.

Free plans/quotas change by provider. Do not assume that every provider is permanently unlimited or free.
