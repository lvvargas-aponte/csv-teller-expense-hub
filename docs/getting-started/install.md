# Install & Run

> Source: `docker-compose.yaml`, `backend/Dockerfile`, `frontend/Dockerfile`, `README.md`

## Prerequisites

- **Docker + Docker Compose** (recommended path), OR
- **Python 3.10+** and **Node 18+** for local development
- A **Google Cloud service account** for the Sheets export ([setup](google-sheets.md))
- A **SimpleFIN** account if you want bank sync ([setup](simplefin.md))
- A **SnapTrade account** if you want investment/crypto holdings sync ([setup](snaptrade.md))
- Optional: **Ollama** for AI features ([setup](ollama.md))

## Option A — Docker (recommended)

```bash
git clone https://github.com/lvvargas-aponte/csv-teller-expense-hub.git
cd csv-teller-expense-hub

# Copy environment template and edit
cp .env.example .env

# Build + start everything (Postgres + backend + frontend)
docker compose up --build
```

- Frontend: <http://localhost:3000>
- Backend: <http://localhost:8000>
- Help (this site): <http://localhost:8000/help/>
- Postgres: localhost on port **15432** (mapped to avoid colliding with a local Postgres)

Stop with `docker compose down`. Logs: `docker compose logs -f`.

## Option B — Local (no Docker)

### Backend

```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate
source venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

You will need a Postgres 16 instance with the **pgvector** extension. The Docker compose file uses `pgvector/pgvector:pg16`.

Set `DATABASE_URL=postgresql+asyncpg://...` in `.env`.

### Frontend

```bash
cd frontend
npm install
npm start
```

Opens at <http://localhost:3000>. The frontend reads `REACT_APP_BACKEND_URL` (defaults to same-origin in production, `http://localhost:8000` in dev compose).

### CSV watcher (optional)

```bash
chmod +x run_csv_watcher.sh
./run_csv_watcher.sh
```

Drop CSV files into `csv_imports/`; processed files move to `csv_imports/processed/`, failures to `csv_imports/failed/`.

## What runs where

| Service | Port | Notes |
|---|---|---|
| `db` (pgvector/pg16) | 15432 (host) → 5432 | Healthcheck-gated; backend waits |
| `backend` (FastAPI) | 8000 | Runs `alembic upgrade head` via `entrypoint.sh` before starting |
| `frontend` (CRA dev server) | 3000 | Hot-reload uses polling (Docker-friendly) |

## Next steps

1. Fill out your `.env` — see [Environment variables](env-vars.md).
2. Connect a bank — see [SimpleFIN setup](simplefin.md).
3. Connect a brokerage — see [SnapTrade setup](snaptrade.md).
4. (Optional) Install Ollama — see [Ollama setup](ollama.md).
