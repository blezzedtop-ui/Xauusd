# Anthropic 3-Model AI Failover

SignalX supports three Anthropic model entries using one `ANTHROPIC_API_KEY`: `ANTHROPIC_MODEL`, `ANTHROPIC_MODEL_2`, and `ANTHROPIC_MODEL_3`.

Expected Railway variables:

```text
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=claude-fable-5
ANTHROPIC_MODEL_2=claude-opus-5
ANTHROPIC_MODEL_3=claude-sonnet-5
```

Each model has its own router entry/cooldown/status. A failure on one Anthropic model advances to the next configured provider instead of stopping the AI validation path.

Anthropic is called through the native Messages API and the shared router validates the returned JSON before accepting the response.
