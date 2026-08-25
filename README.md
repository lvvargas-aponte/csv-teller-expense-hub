# Fin
*Personal finance and shared expenses, with a local AI advisor.*

## 🎯 Overview
This app helps you:
- Connect bank accounts via SimpleFIN and pull transactions directly from the UI
- Auto-import CSV files from Discover & Barclays
- Review and mark shared expenses, then send them to Google Sheets
- Track live account balances and net worth (SimpleFIN + manually added accounts)
- Plan debt payoff with avalanche or snowball strategy
- Get AI-powered spending insights via a local LLM (optional)
- Chat with a virtual finance advisor that sees your transactions, balances, and shared splits (optional)

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
├── run_csv_watcher.sh
├── .env                         # ← create from .env.example (do not commit)
├── docs/
│   └── QUICK_START.md
├── backend/
│   ├── Dockerfile
│   ├── main.py
│   ├── config.py
│   ├── csv_parser.py
│   ├── gsheet_integration.py
│   ├── csv_watcher_script.py
│   ├── requirements.txt
│   ├── manual_accounts.json     # ← auto-created; stores manually-added balances
│   └── credentials.json         # ← add this (do not commit)
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       ├── App.js               # shell: header, nav, routing
│       ├── index.js
│       ├── index.css
│       ├── utils/
│       │   └── formatting.js
│       └── components/
│           ├── FinancesPage.js  # Balances + Payoff Planner + Insights
│           ├── AccountsModal.js
│           ├── SyncModal.js
│           ├── EditModal.js
│           ├── NoteModal.js
│           └── ...
└── csv_imports/                 # created automatically
    ├── processed/
    └── failed/
```

> SimpleFIN needs no certificates or app registration — connecting a bank is just pasting a Setup Token in the UI (see below).

---

## 🔄 Workflow

The app has two pages, selectable from the tabs in the header:

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

#### Account Balances
- Shows live balances pulled from all connected SimpleFIN accounts
- Displays net worth (cash + savings minus credit debt)
- Click **+ Add Account** to manually add a bank or account not connected via SimpleFIN — these are saved to `backend/manual_accounts.json` and persist across restarts
- Manually added accounts show a **Manual** badge and can be removed with ✕

#### Debt Payoff Planner
- Credit accounts from SimpleFIN are pre-filled automatically; add more rows manually
- Choose **Avalanche** (highest APR first — minimises total interest) or **Snowball** (lowest balance first — faster early wins)
- Enter an optional extra monthly payment to see how much interest you save
- Click **Calculate** to see the payoff date and total interest per account
- Click **🤖 Ask AI Advisor** for personalised advice from a local Llama model (requires Ollama)

#### Spending Insights
- Click **✨ Show Insights** to load an AI-powered breakdown of your spending
- Shows spending by category for the last 3 months, a next-month forecast, and an AI summary
- Requires Ollama running locally (`ollama serve`); a nudge card is shown if it isn't available

#### Virtual Advisor (chat) — "Fin"
- Switch to the **🤖 Advisor** tab on the Finances page to chat with a household-finance advisor and friend
- Fin runs a bounded tool-use loop over a **local** Ollama LLM: it sees a lean facts header plus a typed tool registry (balances, transactions, budgets, goals, holdings, documents, past chats, personal memory) and decides what to look up. Every turn's reasoning chain is persisted as JSONB on `conversation_turns.trajectory` for inspection and offline eval.
- With `ADVISOR_WEB_TOOLS_ENABLED=true` (default), Fin can also reach live market data (`get_stock_quote` / `get_stock_history` / `get_stock_fundamentals` via yfinance) and the open web (`web_search` via DuckDuckGo, `fetch_webpage` with SSRF guards) — so it can give direct, opinionated answers on strategy questions
- Fin learns about you over time: a background job proposes durable personal facts from your chats into the Memory panel (confirm/reject), and a style profile adapts its voice every ~10 turns
- Conversations persist to Postgres (`json_stores` + `conversation_turns` tables) — re-open past chats from the sidebar, delete any you don't need
- Ask things like:
  - *"How did our dining spending change this month?"*
  - *"Should I keep the stocks I have?"*
  - *"I have some extra money this month — which stocks should I invest in?"*
- Requires Ollama running locally. The chat endpoint uses `OLLAMA_CHAT_MODEL` (defaults to `OLLAMA_MODEL`); Qwen 2.5 14B+ (or comparable) recommended for reliable local tool-calling. See [docs/concepts/advisor.md](docs/concepts/advisor.md) for the tool catalog, guards, and CI coverage.

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

## 📝 Notes

- **Transactions** live in memory until sent to Google Sheets. Restarting the app clears the queue.
- **Manually added balances** are persisted to `backend/manual_accounts.json` and survive restarts.
- All transaction sources (SimpleFIN + CSVs) appear together in one review table.
- The CSV watcher processes files one at a time.
- MIT License — feel free to fork and adapt for your household.
