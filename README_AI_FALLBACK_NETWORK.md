# Multi-AI Fallback Network

The dashboard only shows AI providers that have the required credentials configured in Railway. Providers without keys are hidden.

Fallback order:
1. Groq GPT-OSS 120B
2. Google Gemini Flash
3. OpenRouter Free
4. Groq Qwen
5. Mistral
6. Cerebras
7. Cloudflare Workers AI
8. DeepSeek
9. OpenAI

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
