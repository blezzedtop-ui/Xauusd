# Phone-only deployment

## Recommended
Deploy this whole folder to Railway as one FastAPI service. The backend serves `index.html`, so the phone uses one HTTPS URL and no PC is required.

## Netlify frontend
Netlify cannot run the FastAPI `main.py` directly. If the frontend stays on Netlify, the FastAPI backend must be hosted separately (Railway/Render/etc.) and `config.js` must contain its public HTTPS URL.

The old local CMD instruction has been removed. The site now shows a cloud-specific error instead of telling phone users to run Python locally.
