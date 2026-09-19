# SignalX 24/7 AI Usage Monitor

This build adds a persistent daily AI usage/quota monitor and a free-first provider router.

## Router

Default order:

`Groq -> Groq #2 -> Gemini -> Cloudflare -> OpenRouter Free -> Hugging Face -> Claude Sonnet -> Claude Opus -> Claude Fable -> DeepSeek -> Mistral -> Cerebras -> OpenAI`

A provider is skipped when disabled, unconfigured, cooling down, rate-limited, or when the site-side Claude budget guard is reached.

## Dashboard

Admin > AI Fallback Network now shows:

- Today API Attempts
- Free Provider Attempts
- Paid Provider Attempts
- Estimated Cost Today
- Total Tokens
- Claude Spend
- Claude daily app budget/remaining
- per-provider requests, failures, tokens, estimated cost, and quota/usage hints

Usage is refreshed every 30 seconds while the section is open.

## Persistence

Daily counters are stored in the `ai_usage_daily` table, so Railway restarts do not erase the usage counters when a persistent PostgreSQL database is configured.

## Environment variables

```env
GROQ_API_KEY_2=
GROQ_MODEL_2=qwen/qwen3.8-27b
HUGGINGFACE_MODEL=Qwen/Qwen3-32B
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-fable-5
ANTHROPIC_MODEL_2=claude-opus-5
ANTHROPIC_MODEL_3=claude-sonnet-5
CLAUDE_DAILY_BUDGET_USD=3
AI_ROUTER_MODE=free_first
AI_FALLBACK_ORDER=groq,groq_2,gemini,cloudflare,openrouter,huggingface,claude_sonnet,claude_opus,claude_fable,deepseek,mistral,cerebras,openai
```

`CLAUDE_DAILY_BUDGET_USD` is a SignalX application safety cap, not an Anthropic account limit.

## Quota assumptions used by the monitor

- Groq free/developer reference values used for the built-in gauge: 1,000 requests/day and 200,000 tokens/day for supported models; Groq documents that limits are organization-level and exposes remaining-limit headers.
- OpenRouter Free: 50 requests/day.
- Cloudflare Workers AI: 10,000 Neurons/day free allocation; this is compute usage, not request count.
- Gemini: quota is model/project/tier dependent, so the UI deliberately labels it dynamic instead of inventing a fixed daily number.
- Hugging Face: account/model dependent, so the UI labels it dynamic.

These values are implementation reference points; provider-side quotas can change and live response headers/statuses should be treated as authoritative.
