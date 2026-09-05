# Financial Freedom
*Self-hosted personal finance and shared expenses, with **Fin** — a local AI advisor.*

## 🎯 Overview
This app helps you:
- Connect bank accounts via SimpleFIN and brokerages via SnapTrade, and pull transactions from the UI
- Auto-import CSV files from Discover & Barclays
- Review, categorise and split transactions, with category rules learned from what you correct
- Settle shared expenses with a partner through a two-way Google Sheet sync — disputes, corrections and a monthly settle-up
- Track live balances, net worth, holdings and a household health score
- Plan debt payoff (avalanche or snowball), budgets, goals, and recurring commitments
- Chat with Fin, an agent grounded in your own data, running entirely on your machine (optional)

Everything runs locally: Postgres + pgvector for storage, Ollama for every AI call. **No cloud LLM is used anywhere.**

> ### ⚠️ Fin is not a financial adviser
> Read [AI advisor disclaimer](#ai-advisor-disclaimer) before acting on anything Fin tells you.

**Full documentation** lives in [`docs/`](docs/index.md) and is served in-app at
`http://localhost:8000/help` (run `mkdocs build` to populate it). This README covers setup and
running; the help site covers every page and button.

---

## 📸 What it looks like

> **Every number below is invented.** These are real screenshots of the app, taken against a
> throwaway demo database seeded by [`backend/scripts/seed_demo.py`](backend/scripts/seed_demo.py)
> — fictional household, fictional banks, fictional balances. See
> [Demo data](#-demo-data-for-screenshots) to run it yourself.

**Home** — net worth split by asset and debt, what needs your attention, and what's due next.

![Home dashboard](docs/assets/screenshots/home.png)

**Transactions** — categorise, split with a partner and mark reviewed; the rail keeps the running
total and where the money went for whatever you're filtered to.

![Transactions](docs/assets/screenshots/transactions-history.png)

**Shared** — one month of split expenses, who owes whom, and the settle-up that closes it. The
same rows live in a Google Sheet both households can see.

![Shared expenses](docs/assets/screenshots/transactions-shared.png)

**Ask Fin** — a local model with tools that read your own data, so the numbers in the answer are
your numbers. Nothing leaves the machine.

![Ask Fin](docs/assets/screenshots/ask-fin.png)

**Plan → Budgets** — monthly caps with pacing: each line projects where it lands at this rate, so
a category going wrong shows up in week one rather than on the last day of the month.

![Budgets](docs/assets/screenshots/plan-budgets.png)

**Plan → Goals** — targets with the monthly contribution each one needs to land on time.

![Goals](docs/assets/screenshots/plan-goals.png)

**Debt** — balances, APRs, and per-card utilisation against the bands a credit score actually
reads, plus what each card needs to drop under the next one.

![Debt](docs/assets/screenshots/debt.png)

---

## 📋 Prerequisites

### 1. Google Cloud Service Account
- Go to [Google Cloud Console](https://console.cloud.google.com)
- Create a new project or select an existing one
- Enable the **Google Sheets API**
- Create a **Service Account** and download the JSON key as `credentials.json`
- Place `credentials.json` in the `backend/` folder
- Share your Google Sheet with the service account email (found in `credentials.json` as `client_email`)

### 2. SimpleFIN Account

> **SimpleFIN isn't free — it's a small flat subscription** ([current pricing](https://beta-bridge.simplefin.org/info/pricing)),
> billed per account holder rather than per linked bank. It's the cheapest honest option here:
> Plaid and its peers don't sell to individuals at all, and the budgeting apps that bundle bank
> sync cost several times more per month and want your data on their servers. A few dollars a
> month buys unlimited CSV-free imports and keeps everything on your own machine. If you'd
> rather not pay at all, skip this step — CSV upload and the watch folder work without it, and
> every other feature works on CSV-imported data.

- Visit [bridge.simplefin.org/simplefin/create](https://bridge.simplefin.org/simplefin/create), link a bank, and copy the one-time **Setup Token** it gives you
- Paste that token into the **🏦 Accounts** panel in the UI — no terminal steps, no API keys to generate up front
- The app exchanges the token for a durable **Access URL** and saves it to `SIMPLEFIN_ACCESS_URLS` in your `.env` automatically

### 3. Google Sheet Setup
- Create a Google Sheet with one worksheet per month, titled `June 2026`, `July 2026`, and so on. A settled month gets a ` - PIF` suffix.
- Each month tab carries these fourteen headers, in this order (swap in your actual names):

  `Transaction Date | Description | Amount | Who | What [PERSON_1_NAME] Owes | What [PERSON_2_NAME] Owes | Notes | Reviewed | Dispute | Dispute By | Dispute Note | Txn ID | Owner | Carried From`

- `Who` is the person who **paid**. Fill only the *other* person's Owes column —
  the payer's cell stays empty.
- The last three columns are the sync's own bookkeeping. `Txn ID` and `Owner` say which
  installation owns a row; sync only ever writes rows it owns, plus the three `Dispute`
  columns on rows it does *not* own. A row with no `Txn ID` is left strictly alone, which is
  how the totals footer and any hand-typed line survive a sync untouched.
- Columns are matched **by header text, never by position**, so the order above is for
  readability — what matters is that every header is present and spelled exactly.
- Copy the Sheet ID from the URL — the string between `/d/` and `/edit`
- Already have months of hand-kept history? `python -m scripts.adopt_worksheets` tags those
  rows so the app can adopt them without retyping. It is a dry run by default — read the plan
  it prints, then re-run with `--apply --i-have-a-backup`.

### 4. Ollama (optional — for AI features)
- Install [Ollama](https://ollama.com) and pull a model. The default is `qwen2.5:14b-instruct` — a strong open-weight model for numeric reasoning that fits comfortably on a moderate GPU (~10 GB VRAM quantized):
  ```bash
  ollama pull qwen2.5:14b-instruct
  ollama serve
  ```
- Model options (all free, all local) — pick based on your hardware:
  - `qwen2.5:14b-instruct` — recommended default (RTX 3060 12GB / 4070 / 4080+)
  - `qwen2.5:7b-instruct` — lighter (~5 GB VRAM), still strong
  - `llama3.1:8b-instruct` — proven baseline
  - `llama3.2:3b` — CPU-friendly fallback for low-spec machines
- Override via env vars: `OLLAMA_MODEL` (default model for insights/advice) and `OLLAMA_CHAT_MODEL` (chat model — defaults to `OLLAMA_MODEL`).
- The app detects Ollama automatically. If it isn't running, AI features show a nudge card instead of an error.

---

## ⚙️ Environment Variables

Create a `.env` file in the project root (copy from `.env.example`):

```bash
# SimpleFIN — connect a bank via the "Connect via SimpleFIN" box in the
# Linked Accounts modal (paste the Setup Token from bridge.simplefin.org).
# The resulting Access URL is saved here automatically — leave this blank.
SIMPLEFIN_ACCESS_URLS=

# SnapTrade — brokerage/crypto holdings (optional)
SNAPTRADE_CLIENT_ID=
SNAPTRADE_CONSUMER_KEY=

# Google Sheets
SPREADSHEET_ID=your_google_sheet_id
SHEET_NAME=Sheet1                # optional: name of the tab

# Customize for your household
PERSON_1_NAME=Alice
PERSON_2_NAME=Bob

# Which of the two people THIS installation belongs to (1 or 2).
INSTANCE_PERSON_SLOT=1

# Two-way shared-expense sync (writes to the spreadsheet). Off by default.
SHEET_SYNC_ENABLED=false

# Ollama (local LLM). Docker reaches the host via host.docker.internal.
OLLAMA_HOST=http://host.docker.internal:11434
OLLAMA_MODEL=qwen2.5:14b-instruct
OLLAMA_CHAT_MODEL=qwen2.5:14b-instruct
OLLAMA_NUM_CTX=16384             # Ollama's own 4096 default truncates Fin's prompt

# Fin's agent loop and its web/market tools. Set web tools false for an
# offline or air-gapped install — Fin degrades to DB-grounded answers.
ADVISOR_AGENT_MAX_ITERS=10
ADVISOR_WEB_TOOLS_ENABLED=true

# CSV Watch Folder
CSV_WATCH_FOLDER=./csv_imports
```

`backend/config.py` is the single source of truth for every environment variable — see
[`.env.example`](.env.example) for the full list with comments, and
[docs/getting-started/env-vars.md](docs/getting-started/env-vars.md) for what each one does.

> **Person names** appear as column headers in your Google Sheet (e.g. "What Alice Owes", "What Bob Owes"). Set them to whatever makes sense for your household.

> ⚠️ **`INSTANCE_PERSON_SLOT` — read this if you ever run a second copy.**
> It says which of the two people this installation belongs to, and it
> **defaults to `1`**. If you and your partner each run your own copy, one of you
> must set it to `2`. Two installations left on the same slot both believe they
> are the same person, and every "who owes whom" figure on one side comes out
> **backwards** — with nothing in the app looking wrong. The two copies must also
> share identical `PERSON_1_NAME` and `PERSON_2_NAME` values, since those become
> the sheet's column headers.

---

## 🚀 Running the App

### Option A: Docker (recommended)

**Requirements:** Docker + Docker Compose

```bash
# Build and start everything
docker compose up --build

# Or run in the background
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

Frontend: **http://localhost:3000** — Backend: **http://localhost:8000** — Help: **http://localhost:8000/help**

Postgres is published on host port **15432** (not 5432, so it can't collide with a local
Postgres): `postgresql://finfree:finfree_dev@localhost:15432/financial_freedom`.

> **After editing `.env`, recreate — don't restart.** Compose reads `env_file` only when it
> *creates* a container, so `docker compose restart` keeps the old values and the change looks
> silently ignored:
> ```bash
> docker compose up -d --force-recreate backend
> ```

Database migrations run with Alembic:

```bash
docker compose run --rm backend alembic upgrade head
```

To also run the CSV watcher:

```bash
chmod +x run_csv_watcher.sh
./run_csv_watcher.sh
```

---

### Option B: Local (No Docker)

**Requirements:** Python 3.11, Node 18+, and a **Postgres 16 with the `pgvector` extension** —
the app has no file-only mode. The simplest split is to run the database in Docker
(`docker compose up db`) and the rest on the host; point `DATABASE_URL` at
`postgresql+asyncpg://finfree:finfree_dev@localhost:15432/financial_freedom`.

#### Backend

```bash
cd backend

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create/upgrade the schema
alembic upgrade head

# Start the API server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Backend runs at **http://localhost:8000**

#### Frontend

In a separate terminal:

```bash
cd frontend
npm install
npm start
```

Frontend runs at **http://localhost:3000**

#### CSV Watcher (optional)

```bash
chmod +x run_csv_watcher.sh
./run_csv_watcher.sh
```

---

## 📂 Project Structure

```
.
├── docker-compose.yaml          # db (pgvector) + backend + frontend + docs builder
├── mkdocs.yml
├── run_csv_watcher.sh
├── .env                         # ← create from .env.example (do not commit)
├── docs/                        # mkdocs source → built into site/, served at /help
│   ├── index.md
│   ├── getting-started/  concepts/  tabs/  modals/  reference/
├── backend/
│   ├── main.py  config.py       # config.py is the ONLY place env vars are read
│   ├── routers/                 # one router per domain (~30)
│   ├── db/                      # async engine, ORM models, one repo per table
│   ├── alembic/versions/        # schema migrations
│   ├── agent/                   # Fin's tool registry, harness, web + market tools
│   ├── sheet_sync/              # two-way Google Sheet contract, diff engine, footer
│   ├── scripts/                 # one-shot tools (worksheet adoption, normalisers)
│   ├── tests/  tests_unit/      # integration (real DB) and unit
│   └── credentials.json         # ← add this (do not commit)
├── frontend/
│   └── src/
│       ├── App.js               # thin shell: routes only
│       ├── navConfig.js         # the one definition of pages, paths and labels
│       ├── api/                 # one client module per domain
│       ├── components/{accounts,finances,settings,shared,transactions,ui}/
│       └── styles/              # tokens.css + one sheet per domain
└── csv_imports/                 # created automatically
    ├── processed/
    └── failed/
```

> SimpleFIN needs no certificates or app registration — connecting a bank is just pasting a Setup Token in the UI (see below).

---

## 🔄 Workflow

Navigation lives in the **sidebar**, not a header bar; help and the dark-mode toggle sit in the
sidebar footer under the health score. There are eight sections:

| Section | What lives there |
|---|---|
| **Home** | Net worth, the health score, and a ranked *Needs you* feed of what wants a decision today |
| **Transactions** | **Current** (review queue), **Shared** (two-person settle-up), **History** (the full record) |
| **Accounts** | What is linked and whether it is healthy — cash, investments, property, manual accounts |
| **Debt** | Cards and loans, utilization, payoff planner, borrowing power |
| **Invest** | Holdings per brokerage, allocation, portfolio quality, fees, retirement projection |
| **Plan** | Budgets, Goals, and Commitments (bills, subscriptions, recurring spend) |
| **Ask** | Fin the advisor, and its Memory — your document and personal-fact library |
| **Settings** | Financial profile, categories and rules |

Each has its own page in the [help site](docs/index.md); the walkthrough below covers the daily loop.

---

### Transactions

#### 1. Connect Bank Accounts

Open the **Accounts** page in the sidebar, then the Linked Accounts panel:
- Visit [bridge.simplefin.org/simplefin/create](https://bridge.simplefin.org/simplefin/create), connect a bank, and copy the Setup Token it gives you
- Paste the token into the **Connect via SimpleFIN** box and click **Connect**
- Connected accounts are listed with their status (Active / Closed / Connection Error / Rate Limited)
- Use **🗑️ Disconnect** to drop a connection (local history stays) or **Delete permanently** to remove an account and its data entirely

The Access URL from a claimed Setup Token is saved automatically to `SIMPLEFIN_ACCESS_URLS` in your `.env` and takes effect immediately without a restart.

#### 2. Import Transactions

**Sync from banks**
1. Click **⟳ Sync Banks**
2. Choose a date range (previous month, this month, or custom)
3. Select which accounts to include — all are checked by default
4. Click **Sync** — transactions are loaded into the review queue

**CSV Upload (manual)**
1. Click **↑ Upload CSV** (Transactions → Current, in the action row) and select a Discover or Barclays CSV file
2. Transactions appear in the review table immediately

**Watch Folder (auto)**
1. Start the CSV watcher
2. Drop CSV files into `csv_imports/`
3. Successfully processed files move to `csv_imports/processed/`, failures to `csv_imports/failed/`

#### 3. Review & Split (Current)

1. Use the filters (bank, type, month, category, search) to focus on the rows you want
2. Click **½** for an even shared split or **P** for personal; **🧮** adjusts an uneven split
3. Bulk-select rows to categorise, split or review many at once
4. Click a row to expand its detail inline — category, note, transfer, split
5. **✨ Suggest** asks the local LLM for categories; you approve them in a preview before anything is written
6. The rail beside the table tracks review progress, the balance of the rows on screen, and where the money went
7. **↗ Send to Sheet** in the same action row syncs the shared rows for the selected month

Marking a row shared, personal, or categorised does **not** mark it reviewed — reviewing is its
own decision, and rows stay in the queue until you make it.

#### 4. Settle up (Shared)

- Every shared row, yours and your partner's, grouped by day with who paid it
- **Dispute** a row you didn't expect and leave a note — it appears on their copy on the next sync
- The settle-up card totals what each side owes and nets it to one figure
- **My rows are complete** publishes a totals footer to the bottom of the month's tab; **Mark paid in full** settles the month and renames its tab with ` - PIF`
- Only rows with a split count toward settle up

> Two-way sync needs `SHEET_SYNC_ENABLED=true`, and each installation must set a different
> `INSTANCE_PERSON_SLOT`. See [docs/tabs/transactions-shared.md](docs/tabs/transactions-shared.md).

---

### Finances pages

#### Home
- Net worth and its composition, plus a household **health score** with per-signal breakdown (hover the ⓘ in the sidebar for how it's weighted)
- A ranked **Needs you** feed — the alerts and insights that actually want a decision today

#### Accounts
- Live balances from every connected SimpleFIN account and SnapTrade brokerage, with connection health per link
- **+ Add Account** records a bank, property or asset that isn't linked anywhere — manual accounts carry a **Manual** badge

#### Debt
- Credit accounts are pre-filled from your linked cards; add more rows manually
- Choose **Avalanche** (highest APR first — minimises total interest) or **Snowball** (lowest balance first — faster early wins)
- Enter an optional extra monthly payment to see how much interest you save, the payoff date, and total interest per account
- Utilization per card and borrowing power (debt-to-income) sit alongside the planner

#### Plan
- **Budgets** per category, with what's left this month
- **Goals** with a target and a contribution pace
- **Commitments** — detected subscriptions and recurring bills, with a review queue for the ones the detector isn't sure about

#### Ask — "Fin"
- Chat with a household-finance advisor grounded in your own data
- Fin runs a bounded tool-use loop over a **local** Ollama LLM: it sees a lean facts header plus a typed tool registry (balances, transactions, budgets, goals, holdings, documents, past chats, personal memory) and decides what to look up. Every turn's reasoning chain is persisted as JSONB on `conversation_turns.trajectory` for inspection and offline eval.
- With `ADVISOR_WEB_TOOLS_ENABLED=true` (default), Fin can also reach live market data (`get_stock_quote` / `get_stock_history` / `get_stock_fundamentals` via yfinance) and the open web (`web_search` via DuckDuckGo, `fetch_webpage` with SSRF guards) — so it can give direct, opinionated answers on strategy questions
- Fin learns about you over time: a background job proposes durable personal facts from your chats into the Memory panel (confirm/reject), and a style profile adapts its voice every ~10 turns
- Conversations persist to Postgres (`json_stores` + `conversation_turns` tables) — re-open past chats from the sidebar, delete any you don't need
- Ask things like:
  - *"How did our dining spending change this month?"*
  - *"Should I keep the stocks I have?"*
  - *"I have some extra money this month — which stocks should I invest in?"*
- Requires Ollama running locally. The chat endpoint uses `OLLAMA_CHAT_MODEL` (defaults to `OLLAMA_MODEL`); Qwen 2.5 14B+ (or comparable) recommended for reliable local tool-calling. See [docs/concepts/advisor.md](docs/concepts/advisor.md) for the tool catalog, guards, and CI coverage.
- **Fin's answers are not financial advice** — see the disclaimer below.

---

<a id="ai-advisor-disclaimer"></a>

## ⚠️ AI Advisor Disclaimer

**Fin is a software feature, not a financial adviser. Nothing this application produces is
financial, investment, tax, accounting, or legal advice, and no part of it is a recommendation
or solicitation to buy, sell, or hold any security or product.**

Please read this before you act on anything Fin, the insights cards, the payoff planner, or any
other computed figure in this app tells you.

- **No adviser relationship.** Using this app creates no fiduciary, advisory, brokerage, or
  professional relationship of any kind. Fin does not know your full circumstances, obligations,
  risk tolerance, or tax position, and it is not registered or licensed with any authority.
- **It will be wrong sometimes.** Fin is a large language model. It can misread your data,
  miscalculate, and state incorrect things with complete confidence — and it can do so about
  live market data and web pages it fetched. Projections, forecasts, payoff dates, and
  retirement figures are arithmetic on assumptions, not predictions. **Past performance does not
  indicate future results, and every investment can lose value.**
- **Verify before you act.** Check anything that matters against your bank, your statements, and
  a qualified professional — an accountant, tax adviser, or licensed financial adviser — before
  making a decision. Treat Fin's output as a starting point for your own thinking, never as the
  final word.
- **Your data, your responsibility.** Balances and transactions come from third-party
  aggregators (SimpleFIN, SnapTrade), CSV files, and a spreadsheet you maintain. They may be
  stale, incomplete, or wrong. Shared-expense figures are a convenience for two people keeping
  their own records; they are not an accounting or a legally binding statement of debt.
- **No warranty, no liability.** This project is provided **"as is", without warranty of any
  kind**, express or implied, including but not limited to the warranties of merchantability,
  fitness for a particular purpose, and non-infringement. To the fullest extent permitted by
  law, the authors and copyright holders are **not liable for any claim, damages, or other
  liability** — including any financial loss — arising from or in connection with this software
  or its use. It is self-hosted software you run and operate yourself; you are solely
  responsible for every decision you make with it. See [LICENSE](LICENSE).

---

## 🛠️ Useful Commands

```bash
# Check backend health
curl http://localhost:8000/health

# Verify Google Sheet connection
curl http://localhost:8000/api/gsheet/verify

# View all transactions in the queue
curl http://localhost:8000/api/transactions/all

# View account balances summary
curl http://localhost:8000/api/balances/summary

# Test CSV upload
curl -X POST http://localhost:8000/api/upload-csv \
  -F "file=@your_statement.csv"
```

### Tests

Run the two suites **separately** — never as one `pytest` invocation. Each conftest forces its
own `DATABASE_URL` at import time, so collecting both in one process binds the engine to
whichever won and produces a wall of confusing errors.

```bash
docker compose run --rm backend pytest tests_unit   # fast, no DB
docker compose run --rm backend pytest tests        # integration, real DB

cd frontend && npm test -- --watchAll=false         # RTL + jest
```

### Docs

```bash
mkdocs build     # writes site/, which the backend serves at /help
```

### 🎭 Demo data (for screenshots)

`docker-compose.demo.yaml` runs a second, throwaway stack — its own Postgres, its own volume,
its own ports (frontend `3010`, backend `8010`, db `15433`) — so it never touches the real
stack's database. Every credential inherited from `.env` is blanked in the override, so the
demo instance cannot reach SimpleFIN, SnapTrade or your Google Sheet, and the household is
renamed to Alex and Sam. The seed script refuses to run against any database whose name
doesn't end in `_demo`.

```bash
docker compose -f docker-compose.demo.yaml -p finfree-demo up -d
docker compose -f docker-compose.demo.yaml -p finfree-demo run --rm backend python -m scripts.seed_demo
# → http://localhost:3010

docker compose -f docker-compose.demo.yaml -p finfree-demo down -v   # -v drops the demo volume
```

Re-running the seed is idempotent: it clears the demo database first and regenerates the same
six accounts, ~230 transactions across six months, budgets, goals and commitments.

---

## 🔍 Troubleshooting

**Edited `.env` but nothing changed?**
- Under Docker, `docker compose restart` does **not** re-read `env_file` — the container keeps the values it was created with. Run `docker compose up -d --force-recreate backend`

**"Connect via SimpleFIN" doesn't work / says failed to connect?**
- Setup Tokens are one-time use — get a fresh one from [bridge.simplefin.org/simplefin/create](https://bridge.simplefin.org/simplefin/create) if a previous attempt already consumed it
- Recreate the backend after manually editing `SIMPLEFIN_ACCESS_URLS` in `.env`

**Bank connection shows "Connection Error"?**
- Disconnect the account and reconnect it via a fresh Setup Token from bridge.simplefin.org

**Bank shows "Rate Limited"?**
- SimpleFIN is throttling requests for that Access URL — wait a while and sync again
- The connection is still valid; no reconnect is needed

**Google Sheets not working?**
- Confirm `credentials.json` is in the `backend/` folder
- Confirm the sheet is shared with the `client_email` from `credentials.json`
- Confirm `SPREADSHEET_ID` matches the URL between `/d/` and `/edit`
- Run `curl http://localhost:8000/api/gsheet/verify` to check the connection — it also reports `headers_match`, which is false when the tab is missing a contract column

**Shared rows sync, but disputes or notes never appear on the sheet?**
- Sync matches rows by `Txn ID`. A row without one is invisible to it — adopt the tab
  (`python -m scripts.adopt_worksheets`) so every legacy row is tagged
- Disputes are only ever written onto rows you do *not* own; a row of yours can't carry your own dispute

**The sheet's totals don't match the app's settle-up figure?**
- The footer sums the columns on the sheet; the app sums the rows it successfully imported. A row
  the app couldn't read (a blank or unparseable date is the usual cause) counts in one and not the
  other. Check `skipped_peer_rows` in the sync response

**CSV files not parsing?**
- With Docker: `docker compose logs backend`
- Without Docker: check the terminal running uvicorn
- Check `csv_imports/failed/` for error logs

**SimpleFIN not pulling transactions?**
- Open **🏦 Accounts** and confirm accounts show as Active
- Confirm `SIMPLEFIN_ACCESS_URLS` in `.env` isn't empty — it's only populated after a successful Setup Token claim

**AI features not working?**
- Make sure Ollama is running: `ollama serve`
- Make sure the model is pulled: `ollama pull qwen2.5:14b-instruct` (or whichever you set via `OLLAMA_MODEL`)
- The app will show a nudge card rather than an error if Ollama is unreachable
- Check `ollama list` to confirm the model name matches `OLLAMA_MODEL` / `OLLAMA_CHAT_MODEL`

---

## 📝 Notes

- **Everything lives in Postgres** (with pgvector for embeddings) and survives restarts. Sending transactions to Google Sheets does not remove them — the full record stays under Transactions → History.
- **Sync is a diff, not an append.** Each run compares the sheet against your records and writes only what changed, so running it twice for the same month is safe. An instance writes only rows it owns, plus the dispute columns on rows it does not.
- All transaction sources (SimpleFIN + CSVs) appear together in one review table.
- The CSV watcher processes files one at a time.
- **AI is local-only by design** — every model call goes to Ollama on your own machine. There is no cloud LLM fallback, and enabling web tools only lets Fin *read* public pages and market data; your financial data is never sent to them.
- MIT License — feel free to fork and adapt for your household. See the [AI advisor disclaimer](#ai-advisor-disclaimer) for the limits of what this software claims to do.
