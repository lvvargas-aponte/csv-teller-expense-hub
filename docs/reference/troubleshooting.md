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

- Ollama unreachable, or `nomic-embed-text` not pulled (`ollama pull nomic-embed-text`)
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

- Make sure the docs were built. From the project root: `mkdocs build`, or `docker compose run --rm docs` if you have no local mkdocs. The output lands in `site/`, which compose mounts read-only into the backend.
- Confirm the backend mount is in place (see `backend/main.py`).
- After rebuilding the Docker image, restart: `docker compose up --build`.

## Fin answers without using any tools, or loops on the same tool

The chat model must support tool calling. Qwen 2.5 14B+ is the tested floor — smaller models emit
malformed `tool_calls` or ignore them entirely.

- Check `OLLAMA_CHAT_MODEL` names a tool-capable model.
- `OLLAMA_NUM_CTX` below 16384 truncates the system prompt and tool schemas, which looks exactly like
  a model that cannot call tools.
- The harness caps iterations at `ADVISOR_AGENT_MAX_ITERS` and forces a final answer rather than
  returning nothing. If you see the same tool called repeatedly, the repeated-call guard is doing its
  job — the reply is still synthesised from what was gathered.

## Shared sync says "refused", or writes nothing

- `SHEET_SYNC_ENABLED` defaults to **`false`**. The two-way sync is opt-in.
- A period already marked **paid** refuses further pushes. Reopen it first.
- Both installs must use identical `PERSON_1_NAME` / `PERSON_2_NAME` and **different**
  `INSTANCE_PERSON_SLOT` values — see [Environment variables](../getting-started/env-vars.md).

## A subscription isn't showing up on Commitments

The detector needs two distinct months of charges — three, plus a steady amount and a recognisable
cadence, if the merchant has no category and no bill-shaped description.

- Brand-new subscriptions simply have not charged enough times yet.
- A re-issued card can split one merchant into two keys, so neither half clears the gates. Use
  **Merge into** on the row.
- If the merchant appears in your transactions but not the list at all, use **+ Add a commitment we
  missed** and declare its cadence — a declared cadence lifts every gate.

See [Plan → Commitments](../tabs/plan-commitments.md).
