# Troubleshooting

## SimpleFIN sync fails with "No SimpleFIN access URLs configured"

- Connect a bank first via **Linked Accounts** → **Connect via SimpleFIN** (paste a Setup Token generated at [bridge.simplefin.org/simplefin/create](https://bridge.simplefin.org/simplefin/create)).
- Confirm `SIMPLEFIN_ACCESS_URLS` was populated in `.env` after connecting; restart the backend if you edited `.env` by hand.

## SimpleFIN sync is rate-limited

- SimpleFIN asks clients to stay under ~24 requests/day per Access URL. Wait and retry, or sync less frequently.

## Google Sheets export not working

- `backend/credentials.json` must exist.
- The Sheet must be shared with the service account `client_email` (Editor).
- `SPREADSHEET_ID` must match the URL between `/d/` and `/edit`.
- Verify:
  ```bash
  curl http://localhost:8000/api/gsheet/verify
  ```

## CSV not parsing

- Inspect the file in `csv_imports/failed/` for an error log.
- Currently supported: **Discover**, **Barclays**. Other formats may need a parser branch.
- `docker compose logs backend` shows the parse error.

## AI features not working

- `ollama serve` is running.
- The model in `OLLAMA_MODEL` (and `OLLAMA_CHAT_MODEL`) is pulled — `ollama list`.
- Verify the server: `curl http://localhost:11434/api/tags`.
- In Docker, `OLLAMA_HOST=http://host.docker.internal:11434` — confirm the host can reach Ollama.

## Embeddings missing for old conversations / transactions

The startup lifespan handler runs `embed_pending_turns()` and `embed_pending_transactions()`. If they fail, the warning is in the logs. Causes:

- Ollama / sentence-transformers model not available
- Postgres connectivity issue

Restart the backend with the AI dependencies in place; the backfill will run again.

## Database migrations didn't run

- The Docker entry script runs `alembic upgrade head`. If you run locally, do this manually:
  ```bash
  cd backend
  alembic upgrade head
  ```
- Confirm `DATABASE_URL` points to a Postgres with the **pgvector** extension installed.

## Help site (`/help/`) returns 404

- Make sure the docs were built: `cd docs && mkdocs build --site-dir site`.
- Confirm the backend mount is in place (see `backend/main.py`).
- After rebuilding the Docker image, restart: `docker compose up --build`.
