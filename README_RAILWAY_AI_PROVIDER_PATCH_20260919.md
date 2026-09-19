# Railway AI provider patch — 2026-09-19

Fixed the three provider/config problems seen on the AI Fallback Network screen:

1. Groq #2 is now the only Qwen Groq slot used by the router. It reads:
   - GROQ_API_KEY_2 (alias GROQ2_API_KEY)
   - GROQ_MODEL_2 (alias GROQ2_MODEL)
   Default model: qwen/qwen3.8-27b
   The legacy Groq Qwen / qwen/qwen3.6-27b slot was removed from the active provider registry and dashboard.

2. OpenRouter calls now send an explicit `Authorization: Bearer <key>` header through the HTTP client instead of relying on SDK header injection. The Railway secret is normalized for accidental quotes or a pasted `Bearer ` prefix. This addresses `Missing Authentication header` when the variable is present.

3. Hugging Face reads HUGGINGFACE_MODEL directly, with the requested default `Qwen/Qwen3-32B`. HUGGINGFACE_API_KEY remains the primary secret name, with HF_TOKEN as a compatibility alias.

The shared AI router still treats all providers as optional and continues to fail over after HTTP errors, timeouts, empty responses, or invalid/non-JSON AI output.

Railway variables expected:
GROQ_API_KEY
GROQ_MODEL
GROQ_API_KEY_2
GROQ_MODEL_2=qwen/qwen3.8-27b
OPENROUTER_API_KEY
HUGGINGFACE_API_KEY
HUGGINGFACE_MODEL=Qwen/Qwen3-32B

After changing Railway variables, redeploy the service so the new process receives the variables.
