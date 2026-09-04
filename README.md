# NetScreen

Lightweight network monitoring and diagnostics platform. Built with Python 3.12, FastAPI, SQLite, SQLAlchemy, httpx, vanilla JavaScript, Docker and GitHub Actions.

## Features

Real ping monitoring with ICMP/TCP fallback, HTTP/HTTPS checks, DNS resolution, historical results, state-change alerts, responsive dashboard, English/Persian direction switching, Docker persistence and optional Telegram configuration.

## Run

```bash
docker compose up -d
```

Open `http://localhost:8000`, API docs at `/api/docs`, health at `/api/health`, and installation docs at `/guide/installation.html`.

Local run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --app-dir backend --reload
```

## API

`GET /api/monitors`, `POST /api/monitors`, `GET /api/monitors/{id}`, `PUT /api/monitors/{id}`, `DELETE /api/monitors/{id}`, `POST /api/monitors/{id}/check`, `GET /api/monitors/{id}/history`, `GET /api/alerts`, `GET /api/stats`, `GET /api/health`.

## Security

Only monitor targets you own or are authorised to test. Secrets belong in `.env`, never source control. Core operation requires no paid service or API key.

## License

MIT
