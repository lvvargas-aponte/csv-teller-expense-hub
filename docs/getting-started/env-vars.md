# Environment variables

> Source: `backend/config.py`, `.env.example`, `docker-compose.yaml`

All settings live in `.env` at the project root (copy from `.env.example`).

## Teller

| Variable | Default | Notes |
|---|---|---|
| `TELLER_APP_ID` | — | Required to enable bank linking |
| `TELLER_ENVIRONMENT` | `sandbox` | `sandbox` \| `development` \| `production` |
| `TELLER_API_KEY` | (empty) | Comma-separated access tokens — managed by the UI; do not edit by hand |
| `TELLER_CERT_PATH` | `./certs/certificate.pem` | Required for non-sandbox |
| `TELLER_KEY_PATH` | `./certs/private_key.pem` | Required for non-sandbox |

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
| `OLLAMA_NUM_CTX` | `16384` | Context window requested per LLM call. Ollama's default (4096) silently truncates the advisor's system prompt + tool schemas. |
| `ADVISOR_AGENT_MAX_ITERS` | `10` | Hard cap on harness iterations per chat turn. The advisor always runs the tool-use loop; recommended chat model: Qwen 2.5 14B+ for reliable tool calling. |
| `ADVISOR_WEB_TOOLS_ENABLED` | `true` | Enables Fin's `web_search`, `fetch_webpage`, and stock quote/history/fundamentals tools. Set `false` for offline installs. |
| `WEB_SEARCH_MAX_RESULTS` | `5` | Max results per `web_search` call (1–10). |
| `ADVISOR_FETCH_TIMEOUT_SEC` | `20` | Total timeout for advisor `fetch_webpage` requests. |
| `ADVISOR_FETCH_MAX_BYTES` | `2097152` | Byte cap for advisor `fetch_webpage` bodies (2 MiB). |

## Database

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | (set by compose) | `postgresql+asyncpg://expense:…@db:5432/expense_hub` |
| `POSTGRES_PASSWORD` | `expense_dev` | Used by the `db` service in `docker-compose.yaml` |
