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
| `SNAPTRADE_CLIENT_ID` | — | Required to enable the Invest page |
| `SNAPTRADE_CONSUMER_KEY` | — | Required to enable the Invest page |

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
| `INSTANCE_PERSON_SLOT` | `1` | Which of the two people **this installation** belongs to. Must be `1` or `2`; the backend refuses to start on any other value. |
| `SHEET_SYNC_ENABLED` | `false` | Enables the two-way shared-expense sync on [Transactions → Shared](../tabs/transactions-shared.md). Off by default — turning it on lets the app **write** to a spreadsheet holding years of settled records, so it is an explicit opt-in. |

!!! warning "If you ever run a second copy, change the slot"

    `INSTANCE_PERSON_SLOT` defaults to `1`. If each person runs their own copy of
    the app, one of them must set it to `2`.

    Two installations left on the same slot both believe they are the same
    person, so one side computes every "who owes whom" figure **backwards** —
    and nothing in the app looks wrong when it happens.

    The two copies must also use **identical** `PERSON_1_NAME` and
    `PERSON_2_NAME` values, because those strings become the sheet's column
    headers. `Christy` on one side and `Christina` on the other means each copy
    looks for a column the other never wrote.

## CSV ingest

| Variable | Default | Notes |
|---|---|---|
| `CSV_WATCH_FOLDER` | `./csv_imports` | Watched by `run_csv_watcher.sh` |

## AI / Ollama

| Variable | Default | Notes |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` (Docker uses `http://host.docker.internal:11434`) | LLM endpoint |
| `OLLAMA_MODEL` | `qwen2.5:14b-instruct` | Default model — insights, categorisation, payoff advice |
| `OLLAMA_CHAT_MODEL` | `OLLAMA_MODEL` | Used by Fin's chat. Must support tool calling. |
| `OLLAMA_NUM_CTX` | `16384` | Context window requested per LLM call. Ollama's default (4096) silently truncates the advisor's system prompt + tool schemas. |
| `ADVISOR_AGENT_MAX_ITERS` | `10` | Hard cap on harness iterations per chat turn. The advisor always runs the tool-use loop; recommended chat model: Qwen 2.5 14B+ for reliable tool calling. |
| `ADVISOR_MEMORY_INJECT_LIMIT` | `30` | How many confirmed user facts are injected into each turn's prompt. |
| `ADVISOR_WEB_TOOLS_ENABLED` | `true` | Enables Fin's `web_search`, `fetch_webpage`, and stock quote/history/fundamentals tools. Set `false` for offline installs. |
| `WEB_SEARCH_MAX_RESULTS` | `5` | Max results per `web_search` call (1–10). |
| `ADVISOR_FETCH_TIMEOUT_SEC` | `20` | Total timeout for advisor `fetch_webpage` requests. |
| `ADVISOR_FETCH_MAX_BYTES` | `2097152` | Byte cap for advisor `fetch_webpage` bodies (2 MiB). |

## Database

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | (set by compose) | `postgresql+asyncpg://finfree:…@db:5432/financial_freedom` |
| `POSTGRES_PASSWORD` | `finfree_dev` | Used by the `db` service in `docker-compose.yaml` |

## Misc

| Variable | Default | Notes |
|---|---|---|
| `DEBUG` | `true` | Error verbosity. Set `false` in production so tracebacks are not returned to the client. |
