# Troubleshooting

## "Connect a Bank" button is missing

- Confirm `TELLER_APP_ID` is set in `.env`.
- Restart the backend after editing `.env`.

## Bank shows "Connection Error"

- Click **↺** on the row in [Linked Accounts](../modals/accounts-modal.md) to re-enroll.
- If it still fails, disconnect and reconnect.

## Bank shows "Rate Limited"

- Teller is throttling. Wait several minutes and retry. The token is still valid.

## Phantom or "test" accounts in the Accounts modal

Stale or fake tokens (`tok_abc…`, `tok_one`, `tok_two`, …) in `TELLER_API_KEY=` produce zombie rows.

```bash
py backend/scripts/prune_tokens.py
```

Lists each token masked, flags suspect ones, and removes interactively.

The backend logs a warning at startup when these are detected — check the logs.

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
