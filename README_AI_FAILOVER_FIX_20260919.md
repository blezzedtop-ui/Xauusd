# SignalX AI Failover Fix — 2026-09-19

## Fixed
- Removed the broken global `OPENAI_GLOBAL_RATE_LIMIT_UNTIL` dependency from module AI validation.
- Added a shared provider router used by AI Smart Analysis, module validators, MSAI, SMC, Algo/SMC, Fibonacci, Trend Channel, Q&A, and other `ai_json_completion` callers.
- Even when `AI_PROVIDER` is set to one provider, it is treated only as the preferred provider; the router automatically falls through to all configured providers.
- Provider failures are isolated with per-provider cooldowns. A 429/quota or similar failure no longer blocks the entire AI network.
- Invalid/non-JSON AI responses are treated as provider failures and the router tries the next provider.
- AI live results remain candle-cached; failure/fallback results use a short cache so a recovered provider can be used again.
- AI Smart Analysis no longer presents failures as specifically “OpenAI” errors.
- Added all providers to the fallback order even when the environment variable is missing/partial.

## Providers supported by the router
Groq, DeepSeek, Gemini, Groq Qwen, OpenRouter, Mistral, Cerebras, Cloudflare Workers AI, Hugging Face, OpenAI.

## Safety
AI is advisory/validation only. Existing deterministic and AutoTrade execution gates remain separate; provider failover does not bypass RR, structure, geometry, or execution protections.


## Railway provider slots
- `GROQ_API_KEY_2` + `GROQ_MODEL_2` are supported as a separate Groq failover slot.
- `GROQ_MODEL_2` can be set to `qwen/qwen3.8-27b`.
- `OPENROUTER_API_KEY` is read directly from Railway and remains in the automatic fallback chain.
- `HUGGINGFACE_MODEL` is supported directly; this can be set to `Qwen/Qwen3-32B`.
- A failure/cooldown on Groq #1 does not disable Groq #2.
