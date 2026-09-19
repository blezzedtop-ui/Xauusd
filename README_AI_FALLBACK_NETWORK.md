# Multi-AI Fallback Network

The dashboard only shows AI providers that have the required credentials configured in Railway. Providers without keys are hidden.

Fallback order (free-first):
1. Groq GPT-OSS 120B
2. Groq Qwen
3. Google Gemini Flash
4. Cerebras
5. Mistral
6. Cloudflare Workers AI
7. Hugging Face
8. OpenRouter Free
9. DeepSeek Flash (paid emergency fallback)
10. Claude models (paid, if configured)
11. OpenAI (paid, if configured)

Status meanings:
- ONLINE — the latest AI request succeeded.
- LIMITED — provider returned a rate-limit/quota response; the exact error/reason is shown in the dashboard.
- OFFLINE — provider returned another API/network/model error; the exact error/reason is shown in the dashboard.
- READY — credentials exist but this provider has not yet been exercised since the latest process start.

Missing-key providers are not displayed and are skipped by the fallback router.

Railway variables for Cloudflare:
- CLOUDFLARE_ACCOUNT_ID
- CLOUDFLARE_API_TOKEN (or CLOUDFLARE_API_KEY)
- CLOUDFLARE_MODEL (optional)

Railway variables for DeepSeek:
- DEEPSEEK_API_KEY
- DEEPSEEK_MODEL (optional)


Hugging Face is enabled when HF_TOKEN (or HUGGINGFACE_API_KEY) is set. Default model: openai/gpt-oss-120b:fastest via https://router.huggingface.co/v1.


Recommended Railway router variables:
- `AI_ROUTER_MODE=order`
- `AI_PAID_FALLBACK_ENABLED=true`
- `AI_FALLBACK_ORDER=groq,groq_2,gemini,cerebras,mistral,cloudflare,huggingface,openrouter,deepseek,anthropic,anthropic_2,anthropic_3,openai`
