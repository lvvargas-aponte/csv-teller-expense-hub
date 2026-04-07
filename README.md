# Bank Statement & Shared Expense Tracker

## 🎯 Overview
This app helps you:
- Pull transactions from already-connected Teller.io bank accounts
- Auto-import CSV files from Discover & Barclays
- Review and mark shared expenses
- Send approved expenses directly to Google Sheets

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
- Connect your bank accounts using the Teller Connect flow (`scripts/teller/teller-connect-app.js`) to obtain **access tokens**
- Access tokens are stored in `TELLER_API_KEY` (comma-separated if you have multiple banks)

### 3. Google Sheet Setup
- Create a Google Sheet with these headers (swap in your actual names):

  `Transaction Date | Description | Amount | Who | What | [PERSON_1_NAME] Owes | [PERSON_2_NAME] Owes | Notes`

- Copy the Sheet ID from the URL — the string between `/d/` and `/edit`

---

## ⚙️ Environment Variables

Create a `.env` file in the `backend/` folder:

```bash
# Teller API
TELLER_ENVIRONMENT=development
TELLER_APP_ID=your_app_id
TELLER_API_KEY=token_bank1,token_bank2   # comma-separated if multiple banks
TELLER_CERT_PATH=path/to/certificate.pem
TELLER_KEY_PATH=path/to/private_key.pem

# Google Sheets
SPREADSHEET_ID=your_google_sheet_id
SHEET_NAME=Sheet1   # optional: name of the tab

# Customize for your household
PERSON_1_NAME=Alice
PERSON_2_NAME=Bob

# CSV Watch Folder
CSV_WATCH_FOLDER=./csv_imports
```

> **Person names** appear as column headers in your Google Sheet (e.g. "Alice Owes", "Bob Owes"). Set them to whatever makes sense for your household.

---

## 🚀 Running the App

You can run locally without Docker, or use Docker — pick whichever is simpler for you.

---

### Option A: Local (No Docker)

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

# Install dependencies
npm install

# Start the dev server
npm start
```

Frontend runs at **http://localhost:3000**

#### CSV Watcher (Optional)

In a third terminal, if you want the watch-folder auto-import:

```bash
chmod +x run_csv_watcher.sh
./run_csv_watcher.sh
```

---

### Option B: Docker

**Requirements:** Docker + Docker Compose

```bash
# Build and start everything
docker-compose up --build

# Or run in the background
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

Frontend: **http://localhost:3000** — Backend: **http://localhost:8000**

To also run the CSV watcher with Docker:

```bash
chmod +x run_csv_watcher.sh
./run_csv_watcher.sh
```

---

## 📂 Project Structure

```
.
├── docker-compose.yml
├── run_csv_watcher.sh
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── backend_main.py
│   ├── csv_parser.py
│   ├── gsheet_integration.py
│   ├── csv_watcher_script.py
│   ├── credentials.json     # ← add this (do not commit)
│   └── .env                 # ← add this (do not commit)
├── frontend/
│   ├── Dockerfile
│   ├── package_json.json
│   └── src/
│       └── App.js
├── scripts/
│   └── teller/
│       ├── index.js               # monthly sync scheduler
│       ├── teller-connect-app.js  # one-time bank connection helper
│       └── setup-env.js
└── csv_imports/             # created automatically
    ├── processed/
    └── failed/
```

---

## 🔄 Workflow

### Importing Transactions

**CSV Upload (manual)**
1. Open the app at http://localhost:3000
2. Click **Upload CSV** and select a Discover or Barclays CSV file
3. Transactions appear in the review table

**Watch Folder (auto)**
1. Start the CSV watcher
2. Drop CSV files into `csv_imports/`
3. Successfully processed files move to `csv_imports/processed/`, failures to `csv_imports/failed/`

**Teller.io (already-connected banks)**

Call the sync endpoint to pull from all connected accounts at once:

```bash
curl -X POST http://localhost:8000/api/teller/sync
```

This reads every access token in `TELLER_API_KEY`, fetches all accounts and transactions, and loads them into the review queue — deduplicating anything already there. You can hit this on startup or add a "Refresh from Banks" button in the frontend.

### Review & Send

1. Review transactions in the table
2. Click **50/50** for an equal split, or **Edit** for a custom split
3. Fill in Who / What / Notes as needed
4. Click **📊 Send to GSheet** — shared transactions are sent to your Google Sheet and cleared from the queue

---

## 🛠️ Useful Commands

```bash
# Verify Google Sheet connection
curl http://localhost:8000/api/gsheet/verify

# Test CSV upload
curl -X POST http://localhost:8000/api/upload-csv \
  -F "file=@your_statement.csv"

# Pull latest transactions from connected banks
curl -X POST http://localhost:8000/api/teller/sync

# View all transactions currently in the queue
curl http://localhost:8000/api/transactions/all
```

---

## 🔍 Troubleshooting

**Google Sheets not working?**
- Confirm `credentials.json` is in the `backend/` folder
- Confirm the sheet is shared with the `client_email` from `credentials.json`
- Confirm `SPREADSHEET_ID` matches the URL between `/d/` and `/edit`
- Run `curl http://localhost:8000/api/gsheet/verify` to check the connection

**CSV files not parsing?**
- With Docker: `docker-compose logs backend`
- Without Docker: check the terminal running uvicorn
- Check `csv_imports/failed/` for error logs

**Teller.io not pulling transactions?**
- Confirm `TELLER_API_KEY` in `.env` contains your actual **access token(s)** (not your App ID)
- If you have multiple banks, separate tokens with commas: `token1,token2`
- Check the environment matches where you enrolled (`sandbox` vs `development`)
- For cert errors, confirm `TELLER_CERT_PATH` and `TELLER_KEY_PATH` point to your downloaded Teller certificates

---

## 📝 Notes

- **No database** — transactions live in memory until sent to Google Sheets. Restarting the app clears the queue.
- All transaction sources (Teller + CSVs) appear together in one review table.
- The CSV watcher processes files one at a time.
- MIT License — feel free to fork and adapt for your household.