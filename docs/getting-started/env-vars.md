# Environment variables

> Source: `backend/config.py`, `.env.example`, `docker-compose.yaml`

All settings live in `.env` at the project root (copy from `.env.example`).

## SimpleFIN (bank sync)

| Variable | Default | Notes |
|---|---|---|
| `SIMPLEFIN_ACCESS_URLS` | (empty) | Comma-separated Access URLs — written automatically after claiming a Setup Token in the Linked Accounts modal; leave blank and don't edit by hand |

## SnapTrade (brokerage / crypto holdings)

| Variable | Default | Notes |
|---|---|---|
| `SNAPTRADE_CLIENT_ID` | — | Required to enable the Investments tab |
| `SNAPTRADE_CONSUMER_KEY` | — | Required to enable the Investments tab |

SnapTrade has no sandbox/production switch — these two credentials are the entire auth surface. The household's `userId` / `userSecret` are registered on first connect and persisted in Postgres (`json_stores` → `snaptrade_creds`), not in `.env`.

## Google Sheets

| Variable | Default | Notes |
|---|---|---|
| `SPREADSHEET_ID` | — | From your Google Sheet URL (between `/d/` and `/edit`) |
| `SHEET_NAME` | `Sheet1` | Tab name to write to |
| `GOOGLE_CREDENTIALS_FILE` | `credentials.json` | Path to service-account JSON; place in `backend/` |

## Household

| Variable | Default | Notes |
|---|---|---|
| `PERSON_1_NAME` | — | Used in Sheet headers and splits UI |
| `PERSON_2_NAME` | — | Used in Sheet headers and splits UI |

## CSV ingest

| Variable | Default | Notes |
|---|---|---|
| `CSV_WATCH_FOLDER` | `./csv_imports` | Watched by `run_csv_watcher.sh` |

## AI / Ollama

| Variable | Default | Notes |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` (Docker uses `http://host.docker.internal:11434`) | LLM endpoint |
| `OLLAMA_MODEL` | `qwen2.5:14b-instruct` | Used by insights + payoff advice |
| `OLLAMA_CHAT_MODEL` | `OLLAMA_MODEL` | Used by the advisor chat |
| `ADVISOR_AGENT_MODE` | `false` | When `true`, the advisor uses a bounded tool-use loop instead of single-shot RAG. See [AI advisor → Agent harness mode](../concepts/advisor.md#agent-harness-mode-opt-in). Recommended chat model: Qwen 2.5 14B+ for reliable tool calling. |
| `ADVISOR_AGENT_MAX_ITERS` | `6` | Hard cap on harness iterations per chat turn. Ignored when `ADVISOR_AGENT_MODE=false`. |

## Database

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | (set by compose) | `postgresql+asyncpg://expense:…@db:5432/expense_hub` |
| `POSTGRES_PASSWORD` | `expense_dev` | Used by the `db` service in `docker-compose.yaml` |
