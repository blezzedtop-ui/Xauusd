# XAUUSD AI Multi-Engine Analyzer — Railway
One web app combining:
1. SIMPLE TRADING Book v1 deterministic engine (10 named chart patterns)
2. The second uploaded site's deterministic 10-strategy engine (`price_action_10_strategies.py`)
3. OpenAI second-opinion validator

Market data: RealMarketAPI (server-side).
Final decision:
- Book + Secondary + OpenAI agree BUY/SELL -> CONFIRMED
- One deterministic engine + OpenAI agree while the other is WAIT -> engine-confirmed status
- Conflicts -> WAIT
API keys stay server-side as Railway environment variables.

Required:
REALMARKET_API_KEY
OPENAI_API_KEY
OPENAI_MODEL
