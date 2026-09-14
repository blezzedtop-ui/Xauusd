# SIGNALX PRO — Security Hardening

- Signal/strategy calculations remain server-side in `main.py`; frontend receives derived results only.
- API docs/OpenAPI are disabled by default (`ENABLE_API_DOCS=false`).
- CORS defaults to approved SignalX/Railway origins instead of `*`.
- Security headers added: nosniff, frame deny, strict referrer policy, permissions policy, HSTS on HTTPS.
- API responses use no-store/no-cache headers to reduce leakage via browser/proxy caches.
- Deployment diagnostics require admin authentication.
- Provider/API secrets remain environment variables; no secret is placed in `config.js` or `app.js`.
- Auto Trading, XAUUSD/EURUSD separation, Entry/SL/TP flow and the existing UI are preserved.

Production: `SECRET_KEY` may be left empty in Railway; the backend automatically generates a cryptographically random runtime secret when it is not configured. A manually configured `SECRET_KEY` takes precedence. `ADMIN_LOGIN` and `ADMIN_PASSWORD` remain configurable in Railway. Do not commit real secrets.
