# Signal History — Persistent Storage

Signal History now keeps the complete signal snapshot in the database row (`signal_history.payload`) including source, timeframe, candle time, direction, confidence, entry, SL, TP, setup quality and outcome data.

## Important for Railway

Railway containers can be redeployed/recreated. For history to survive redeploys, the app should use Railway PostgreSQL by setting the app service's `DATABASE_URL` to the PostgreSQL service's connection variable/reference.

The app already supports both PostgreSQL and SQLite. SQLite is useful for local testing, but is not persistent across Railway service replacement unless a durable volume is configured.

## Verification

After deployment, the authenticated endpoint below reports the storage backend and history row count:

`GET /api/v1/signals/storage`

Expected production response includes:

- `backend: postgresql`
- `persistent_across_railway_redeploy: true`
- `signal_history_rows: <number>`

No passwords or API keys are stored in the signal snapshot.
