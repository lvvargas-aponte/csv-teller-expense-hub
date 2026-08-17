# Personal Finance Hub

A self-hosted wealth engine for a household that buys and holds rental property: tenants amortize the mortgages, the mortgages finish, and the rental income carries you out of the W2 job.

It started as a shared-expense tracker and still does that. What it mainly does now is answer forward-looking questions.

## 🎯 What it answers

| Question | Where |
|---|---|
| What can I spend today without derailing anything? | **Today** — a goal-funded daily envelope; overspending lowers tomorrow by construction |
| What should I do right now? | **Today** — ranked, dated, dollar-quantified actions from eleven deterministic rules |
| How much of that mortgage payment was principal? | **Loans** — a real amortization schedule, to the cent |
| How is each rental actually performing? | **Properties** — NOI, DSCR, cash-on-cash, pro forma vs. tagged actuals |
| How much equity could I borrow, and what would it cost? | **Equity & Deals** — every extractable figure paired with its payment increase |
| Where should this spare $500 go? | **Spare Money** — a strict waterfall, with the skipped tiers explained |
| When can I retire, and on what? | **Retirement** — deterministic projection to the first *sustainable* year |
| Should I pay this off or invest it? | **Spare Money** — guaranteed returns and hoped-for ones, labelled apart |

Plus what it always did: SimpleFIN bank sync, Discover/Barclays CSV import, shared-expense splits to Google Sheets, budgets, goals, bills, investment holdings via SnapTrade, and a local-LLM advisor.

Everything runs on your own machine. No account, no cloud, no telemetry — the only outbound calls are the ones you configure (SimpleFIN, SnapTrade, Google Sheets) and a local Ollama.

**Full documentation** is served in-app at `/help`, or build it with `mkdocs build`.

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
- Visit [bridge.simplefin.org/simplefin/create](https://bridge.simplefin.org/simplefin/create), link a bank, and copy the one-time **Setup Token** it gives you
- Paste that token into the **🏦 Accounts** panel in the UI — no terminal steps, no API keys to generate up front
- The app exchanges the token for a durable **Access URL** and saves it to `SIMPLEFIN_ACCESS_URLS` in your `.env` automatically

### 3. Google Sheet Setup
- Create a Google Sheet with these headers (swap in your actual names):

  `Transaction Date | Description | Amount | Who | What | [PERSON_1_NAME] Owes | [PERSON_2_NAME] Owes | Notes`

- Copy the Sheet ID from the URL — the string between `/d/` and `/edit`

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

# Google Sheets
SPREADSHEET_ID=your_google_sheet_id
SHEET_NAME=Sheet1                # optional: name of the tab

# Customize for your household
PERSON_1_NAME=Alice
PERSON_2_NAME=Bob

# CSV Watch Folder
CSV_WATCH_FOLDER=./csv_imports
```

> **Person names** appear as column headers in your Google Sheet (e.g. "Alice Owes", "Bob Owes"). Set them to whatever makes sense for your household.

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

Frontend: **http://localhost:3000** — Backend: **http://localhost:8000**

To also run the CSV watcher:

```bash
chmod +x run_csv_watcher.sh
./run_csv_watcher.sh
```

---

### Option B: Local (No Docker)

**Requirements:** Python 3.10+, Node 18+

#### Backend

```bash
cd backend

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

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
├── docker-compose.yaml
├── mkdocs.yml                   # in-app help, served at /help
├── docs/                        # the real documentation
├── .env                         # ← create from .env.example (do not commit)
├── backend/
│   ├── main.py                  # wires ~20 routers under /api
│   ├── analytics.py             # shared business logic; routers stay thin
│   ├── amortization.py          # pure, Decimal-internal loan math
│   ├── properties.py            # rental economics, equity, deal analysis
│   ├── retirement.py            # deterministic projection
│   ├── allocation.py            # the spare-money waterfall
│   ├── coach.py                 # the rule set behind Today and Alerts
│   ├── bills.py  debt_payments.py  csv_parser.py  categorizer.py
│   ├── agent/                   # Fin's tool-use harness + registry
│   ├── db/                      # typed SQLAlchemy repos (Protocol + Pg + InMemory)
│   ├── alembic/versions/        # migrations; run automatically on boot
│   ├── routers/                 # HTTP only
│   ├── tests_unit/              # no database required
│   ├── tests/                   # integration; needs Postgres
│   └── credentials.json         # ← add this (do not commit)
├── frontend/
│   └── src/
│       ├── api/                 # one module per domain, all axios
│       ├── utils/
│       └── components/
│           ├── finances/        # TodayPage, PropertiesPage, LoansPage,
│           │                    # EquityPage, AllocatePage, RetirementPage,
│           │                    # DashboardTab, cards/, payoff/, …
│           └── ui/              # Field, Select, Spin, KpiCard, …
└── csv_imports/                 # created automatically
    ├── processed/
    └── failed/
```

**Where the logic lives.** Routers are HTTP adapters and nothing else; business logic sits in `analytics.py` or a domain module beside it. `amortization.py`, `retirement.py` and `allocation.py` import no state at all — hand them a dataclass, get an answer, no database and no clock beyond the `as_of` you pass. That's why they're covered by a unit suite that runs offline.

**Two persistence styles, on purpose.** Transactions, budgets, goals and account metadata are JSONB blobs behind a dict-shaped facade (`store.py`), because their shape changes constantly. Properties, valuations, loans, holdings and balance snapshots are typed tables with real foreign keys, because they have relational shape and money precision matters across a 360-month schedule.

> SimpleFIN needs no certificates or app registration — connecting a bank is just pasting a Setup Token in the UI (see below).

---

## 🔄 Workflow

Two top-level pages in the header — **Transactions** for review and splits, **Finances** for everything else. Finances has its own sidebar, grouped by what you're trying to do rather than by data type:

---

### Transactions page

#### 1. Connect Bank Accounts

Click **🏦 Accounts** in the header to open the Linked Accounts panel:
- Visit [bridge.simplefin.org/simplefin/create](https://bridge.simplefin.org/simplefin/create), connect a bank, and copy the Setup Token it gives you
- Paste the token into the **Connect via SimpleFIN** box and click **Connect**
- Connected accounts are listed with their status (Active / Closed / Connection Error / Rate Limited)
- Use **🗑️ Disconnect** to drop a connection (local history stays) or **Delete permanently** to remove an account and its data entirely

The Access URL from a claimed Setup Token is saved automatically to `SIMPLEFIN_ACCESS_URLS` in your `.env` and takes effect immediately without a restart.

#### 2. Import Transactions

**Sync from banks**
1. Click **⟳ Sync Banks** in the header
2. Choose a date range (previous month, this month, or custom)
3. Select which accounts to include — all are checked by default
4. Click **Sync** — transactions are loaded into the review queue

**CSV Upload (manual)**
1. Click **📂 Upload CSV** (on the Transactions page, above the filters) and select a Discover or Barclays CSV file
2. Transactions appear in the review table immediately

**Watch Folder (auto)**
1. Start the CSV watcher
2. Drop CSV files into `csv_imports/`
3. Successfully processed files move to `csv_imports/processed/`, failures to `csv_imports/failed/`

#### 3. Review & Send

1. Use the filters (bank, type, month) to focus on the transactions you want
2. Click **50/50** to mark a shared equal split, or **🧮** for a custom amount
3. Bulk-select rows and use **✓ Mark shared** or **Mark personal** to process many at once
4. Click **🗒️** to add a note (icon becomes **📝** once saved)
5. Click **📊 Send to Sheet** (on the Transactions page, above the filters) — shared transactions go to Google Sheets and are cleared from the queue

---

### Finances page

Deep-linkable at `/finances/<tab>`.

| Section | Tabs |
|---|---|
| **Overview** | Today · Dashboard · Accounts |
| **Spending** | Spending · Budgets · Bills |
| **Debt** | Payoff Plan · Loans |
| **Wealth** | Spare Money · Properties · Equity & Deals · Investments · Goals |
| **Future** | Retirement |
| **Tools** | Knowledge · Ask Fin |

#### Today
One number in large type: what you can spend today without derailing a bill, a debt minimum, or a goal contribution. Below it, the ranked next actions.

The daily figure is `(income − bills − debt minimums − goal contributions − spent so far) ÷ days left`, recomputed on every load. There is deliberately no carry-over ledger — overspending lowers tomorrow because the arithmetic says so, not because a second store is tracking it.

When no income can be detected, it says so instead of guessing. That refusal is the feature.

#### Properties & Loans
Add a property with its purchase price, rent, and full operating-expense model, then attach loans. You get NOI (excluding debt service — the classic error), DSCR, cap rate, cash-on-cash, LTV, equity, and a performance rating with quantified reasons.

Loans produce a real amortization schedule. **`GET /api/loans/{id}/current-payment` answers "how much of this month's payment is principal"** and matches a servicer statement to the cent — `Decimal` internally, `float` at the boundary.

Tag transactions to a property and the page reports pro forma and actuals side by side, never blended, each labelled with how many months of data stand behind it.

#### Equity & Deals
Cash-out refinance and HELOC scenarios per property. Every extractable amount is rendered with its new payment, the payment delta, the DSCR that survives it, and the resulting cash flow — because a number that looks like free money is actually a payment increase.

The deal analyzer's headline is **portfolio** cash flow, not the deal's: a purchase funded by a HELOC on something you already own can look positive standalone and still reduce your monthly income.

#### Spare Money
A strict waterfall — employer match → emergency buffer → debt above your expected return → tax-advantaged room → property fund → brokerage or extra principal. Each tier takes what it needs and passes the rest down.

Unknown inputs produce a question, not an assumption. Guaranteed returns and projected ones are labelled apart. And the **skipped** list is half the answer, because "why not just pay off the house?" is the question that actually gets asked.

#### Retirement
The mechanic it exists to show: rent drifts up with inflation, a fixed mortgage payment doesn't, and then the mortgage *ends* — and that property's cash flow jumps by the whole payment, permanently.

"Earliest retirement year" means the first year that works **and keeps working**. A crossing that later reverses when inflation outruns a fixed income stream isn't a retirement date.

Deterministic, with three sensitivity rows instead of a Monte Carlo probability that assumptions this soft couldn't honestly support.

#### Debt Payoff Planner
- Credit accounts from SimpleFIN are pre-filled automatically; add more rows manually
- **Avalanche** (highest APR first) or **Snowball** (lowest balance first)
- A freed-up minimum payment rolls into the next debt — that cascade is the defining mechanic of both strategies
- Mortgages are tracked but excluded from the simulation: ranking on APR alone would send the extra payment to a 3% mortgage ahead of a 29% card
- **🤖 Ask AI Advisor** for a narrative on the plan (requires Ollama)

#### Dashboard
Eleven cards in a narrative arc — Position → Flow → Trend → Assets → Constraints → Commitments → Signals. **⠿ Arrange cards** makes the grid draggable and resizable; it's off by default so a stray drag on a chart doesn't rearrange a screen you were only reading.

#### Virtual Advisor (chat) — "Fin"
- Switch to the **🤖 Advisor** tab on the Finances page to chat with a household-finance advisor
- The advisor is grounded in your real data: cached balances, last 6 months of spending, credit-card debt, and the recent shared-expense split
- Conversations persist to Postgres (`json_stores` + `conversation_turns` tables) — re-open past chats from the sidebar, delete any you don't need
- Ask things like:
  - *"How did our dining spending change this month?"*
  - *"Are our shared splits fair between the two of us?"*
  - *"Can I afford $300 extra toward my credit card debt?"*
- Requires Ollama running locally. The chat endpoint uses `OLLAMA_CHAT_MODEL` (defaults to `OLLAMA_MODEL`).

**Two execution modes** (controlled by `ADVISOR_AGENT_MODE`):

- **RAG mode (default, `false`)** — single-shot: a full financial snapshot + similar past turns / transactions / documents are stuffed into one system prompt, then one call to Ollama.
- **Agent mode (opt-in, `true`)** — bounded tool-use loop: Fin sees a lean facts header plus a typed tool registry and decides what to look up. Seventeen tools, covering transactions, balances, debt, budgets, goals, spending roll-ups, investments, cashflow, documents, memory — plus `get_safe_to_spend`, `get_properties`, `get_usable_equity`, `project_retirement` and `get_next_actions`. Every turn's reasoning chain is persisted as JSONB on `conversation_turns.trajectory` for inspection and offline eval.

  The registry is capped at seventeen by a unit test, because local-model *selection* accuracy degrades before the context window does. `get_next_actions` returns the Today page's list verbatim so chat and the app can't disagree about what to do; `project_retirement` samples five years rather than dumping fifty.

  Requires Qwen 2.5 14B+ (or comparable) for reliable local tool-calling. See [docs/concepts/advisor.md → Agent harness mode](docs/concepts/advisor.md#agent-harness-mode-opt-in) for the tool catalog, guards (max iterations, hallucinated tool, repeated call, invalid args), and CI coverage.

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

---

## 🔍 Troubleshooting

**"Connect via SimpleFIN" doesn't work / says failed to connect?**
- Setup Tokens are one-time use — get a fresh one from [bridge.simplefin.org/simplefin/create](https://bridge.simplefin.org/simplefin/create) if a previous attempt already consumed it
- Restart the backend after manually editing `SIMPLEFIN_ACCESS_URLS` in `.env`

**Bank connection shows "Connection Error"?**
- Disconnect the account and reconnect it via a fresh Setup Token from bridge.simplefin.org

**Bank shows "Rate Limited"?**
- SimpleFIN is throttling requests for that Access URL — wait a while and sync again
- The connection is still valid; no reconnect is needed

**Google Sheets not working?**
- Confirm `credentials.json` is in the `backend/` folder
- Confirm the sheet is shared with the `client_email` from `credentials.json`
- Confirm `SPREADSHEET_ID` matches the URL between `/d/` and `/edit`
- Run `curl http://localhost:8000/api/gsheet/verify` to check the connection

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

## ✅ Tests

```bash
# Backend, no database needed — must stay green offline
docker compose exec backend python -m pytest tests_unit -q

# Backend integration (needs Postgres)
docker compose exec backend python -m pytest tests -q

# Frontend
docker compose exec frontend npx craco test --watchAll=false

# Docs must build clean
mkdocs build --strict
```

> **The backend does not hot-reload.** After changing Python, run `docker compose restart backend` or you'll be testing the old code.

---

## 📝 Notes

- **Everything persists to Postgres.** Transactions, balances, budgets, goals, properties, loans and conversations all survive restarts; Alembic migrations run automatically on boot.
- All transaction sources (SimpleFIN + CSVs) appear together in one review table.
- The CSV watcher processes files one at a time.
- **Single household, no auth.** Every single-row table is keyed `'household'`. This is designed to run on your own machine — don't expose it to the internet as-is.
- **Property valuations are user-entered**, and equity, LTV and the entire retirement projection inherit that subjectivity. The UI shows `as_of` dates prominently rather than implying precision the data doesn't have.
- **It won't tell you to sell a property.** It surfaces quantified reasons — negative cash flow, DSCR under 1.0, cash-on-cash below what an index fund would return — and leaves the decision to you.
- MIT License — feel free to fork and adapt for your household.
