# SignalX security setup

Before first Railway deploy:

1. Create a strong `ADMIN_LOGIN` and `ADMIN_PASSWORD`.
2. Generate one stable random `SECRET_KEY` and store it in Railway Variables.
3. Set `DATABASE_URL` to the Railway PostgreSQL service.
4. Never commit `.env`, database files, API keys, or backups.
5. Keep `MT5_BRIDGE_TOKEN` private and rotate it if exposed.

The application intentionally fails fast when required admin credentials or `SECRET_KEY` are missing.
