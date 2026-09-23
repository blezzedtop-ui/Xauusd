# Free AI mode

This build uses a free-first AI provider strategy.

- `AI_PROVIDER=auto` (recommended)
- `GROQ_API_KEY` enables Groq free-plan inference.
- Default model: `openai/gpt-oss-120b`.
- If Groq is unavailable and `OPENAI_API_KEY` is set, the app falls back to OpenAI.
- If neither provider is configured, the deterministic Quant/ICT/SNR/Classic/Risk engines continue to work without AI.

The AI layer never fetches market prices itself. It validates the technical context already derived from the TradingView candle feed.

## Railway variables

Set:

```text
AI_PROVIDER=auto
GROQ_API_KEY=your_groq_key
GROQ_MODEL=openai/gpt-oss-120b
```

Keep your keys only in Railway Variables / Secrets; never commit them to GitHub.
