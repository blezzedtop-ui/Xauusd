# XAUUSD AI Multi-Engine — Railway + GitHub

Railway deployment uses **Railpack** (not Dockerfile) to avoid Docker build-context failures.

## Structure
- `main.py` — FastAPI backend
- `price_action_10_strategies.py` — secondary strategy engine
- `frontend/index.html` — TradingView Lightweight Charts UI
- `requirements.txt` — Python dependencies
- `Procfile` — Railway start command
- `railway.toml` — Railway config

## Railway Variables
Set these in Railway Variables; never commit secrets:
- `REALMARKET_API_KEY`
- `OPENAI_API_KEY`
- `OPENAI_MODEL=gpt-5.6-luna`

## Start
Railway runs:
`uvicorn main:app --host 0.0.0.0 --port $PORT`
