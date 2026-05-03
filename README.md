# Bank Statement & Shared Expense Tracker

## 🎯 Overview
This app helps you:
- Connect bank accounts via Teller.io and pull transactions directly from the UI
- Auto-import CSV files from Discover & Barclays
- Review and mark shared expenses, then send them to Google Sheets
- Track live account balances and net worth (Teller + manually added accounts)
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

### 2. Teller.io Account
- Sign up at [Teller.io](https://teller.io) and get your **Application ID**
- Set `TELLER_APP_ID` in your `.env` — the app handles the rest
- Bank connections and access tokens are managed entirely from the **🏦 Accounts** button in the UI; no terminal steps required

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
# Teller API
TELLER_ENVIRONMENT=sandbox       # sandbox | development | production
TELLER_APP_ID=your_app_id
TELLER_API_KEY=                  # leave blank — tokens are saved automatically from the UI
TELLER_CERT_PATH=./certs/certificate.pem
TELLER_KEY_PATH=./certs/private_key.pem

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
├── certs/                       # Teller mTLS certificates (non-sandbox only)
│   ├── certificate.pem
│   └── private_key.pem
└── csv_imports/                 # created automatically
    ├── processed/
    └── failed/
```

---

## 🔄 Workflow

The app has two pages, selectable from the tabs in the header:

---

### Transactions page

#### 1. Connect Bank Accounts

Click **🏦 Accounts** in the header to open the Accounts panel:
- Click **+ Connect a Bank** to link a new bank account through the Teller Connect popup
- Connected accounts are listed with their status (Active / Closed / Connection Error / Rate Limited)
- Use **↺** to re-authenticate a broken connection, or **🗑️ Disconnect** to remove an account

Access tokens are saved automatically to `TELLER_API_KEY` in your `.env` and take effect immediately without a restart.

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
- Shows live balances pulled from all connected Teller accounts
- Displays net worth (cash + savings minus credit debt)
- Click **+ Add Account** to manually add a bank or account not connected via Teller — these are saved to `backend/manual_accounts.json` and persist across restarts
- Manually added accounts show a **Manual** badge and can be removed with ✕

#### Debt Payoff Planner
- Credit accounts from Teller are pre-filled automatically; add more rows manually
- Choose **Avalanche** (highest APR first — minimises total interest) or **Snowball** (lowest balance first — faster early wins)
- Enter an optional extra monthly payment to see how much interest you save
- Click **Calculate** to see the payoff date and total interest per account
- Click **🤖 Ask AI Advisor** for personalised advice from a local Llama model (requires Ollama)

#### Spending Insights
- Click **✨ Show Insights** to load an AI-powered breakdown of your spending
- Shows spending by category for the last 3 months, a next-month forecast, and an AI summary
- Requires Ollama running locally (`ollama serve`); a nudge card is shown if it isn't available

#### Virtual Advisor (chat)
- Switch to the **🤖 Advisor** tab on the Finances page to chat with a household-finance advisor
- The advisor is grounded in your real data: cached balances, last 6 months of spending, credit-card debt, and the recent shared-expense split
- Conversations persist to `backend/conversations.json` — re-open past chats from the sidebar, delete any you don't need
- Ask things like:
  - *"How did our dining spending change this month?"*
  - *"Are our shared splits fair between the two of us?"*
  - *"Can I afford $300 extra toward my credit card debt?"*
- Requires Ollama running locally. The chat endpoint uses `OLLAMA_CHAT_MODEL` (defaults to `OLLAMA_MODEL`).

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

**"Connect a Bank" button missing?**
- Check that `TELLER_APP_ID` is set in `.env`
- Restart the backend after editing `.env`

**Bank connection shows "Connection Error"?**
- Click **↺** on the account row to re-authenticate
- If the error persists, disconnect and reconnect the account

**Phantom or "test" accounts in the Accounts modal?**
- Usually caused by stale or fake tokens stuck in `TELLER_API_KEY=` (e.g. `tok_abc…`, `tok_one`, `tok_two` left over from earlier test runs). Each bad token produces one "Connection Error" row.
- Run `py backend/scripts/prune_tokens.py` from the repo root — it lists every token masked, flags ones that look synthetic, and lets you remove them interactively. Non-destructive; each removal requires confirmation.
- On startup the backend now logs a warning when it sees test-looking tokens, so you don't have to hunt for them.

**Bank shows "Rate Limited"?**
- Teller is throttling requests — wait a few minutes and sync again
- The token is still valid; no re-authentication is needed

**Google Sheets not working?**
- Confirm `credentials.json` is in the `backend/` folder
- Confirm the sheet is shared with the `client_email` from `credentials.json`
- Confirm `SPREADSHEET_ID` matches the URL between `/d/` and `/edit`
- Run `curl http://localhost:8000/api/gsheet/verify` to check the connection

**CSV files not parsing?**
- With Docker: `docker compose logs backend`
- Without Docker: check the terminal running uvicorn
- Check `csv_imports/failed/` for error logs

**Teller not pulling transactions?**
- Open **🏦 Accounts** and confirm accounts show as Active
- Check that `TELLER_ENVIRONMENT` in `.env` matches where you enrolled (`sandbox` vs `development`)
- For cert errors (non-sandbox), confirm `TELLER_CERT_PATH` and `TELLER_KEY_PATH` point to your Teller certificates

**AI features not working?**
- Make sure Ollama is running: `ollama serve`
- Make sure the model is pulled: `ollama pull qwen2.5:14b-instruct` (or whichever you set via `OLLAMA_MODEL`)
- The app will show a nudge card rather than an error if Ollama is unreachable
- Check `ollama list` to confirm the model name matches `OLLAMA_MODEL` / `OLLAMA_CHAT_MODEL`

---

## 📝 Notes

- **Transactions** live in memory until sent to Google Sheets. Restarting the app clears the queue.
- **Manually added balances** are persisted to `backend/manual_accounts.json` and survive restarts.
- All transaction sources (Teller + CSVs) appear together in one review table.
- The CSV watcher processes files one at a time.
- MIT License — feel free to fork and adapt for your household.
