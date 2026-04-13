# Quick Start Checklist

Follow these steps to get csv-teller-expense-hub running:

## ✅ Pre-Setup

- [ ] Clone the repo: `git clone https://github.com/lvvargas-aponte/csv-teller-expense-hub.git`
- [ ] Have Docker installed on your machine

## ✅ Google Cloud Setup (one-time)

1. - [ ] Go to [Google Cloud Console](https://console.cloud.google.com)
2. - [ ] Create a new project (or select existing)
3. - [ ] Enable the **Google Sheets API**
4. - [ ] Create a **Service Account** and download the JSON key
5. - [ ] Save it as `credentials.json` in the `backend/` folder

## ✅ Google Sheet Setup

1. - [ ] Create a new Google Sheet
2. - [ ] Add these headers in Row 1:
```
Transaction Date | Description | Amount | Who | What | [YOUR_NAME] Owes | [PARTNER_NAME] Owes | Notes
```
Replace `[YOUR_NAME]` and `[PARTNER_NAME]` with actual names (e.g., "Alice Owes | Bob Owes")
- [ ] Copy the Sheet ID from the URL (between `/d/` and `/edit`)
- [ ] **Share the sheet** with the service account email
   - Find it in `credentials.json` under `client_email`
   - Click "Share" in Google Sheets → paste the email → give "Editor" access

## ✅ Configure Environment

1. - [ ] Copy `.env.example` to `.env` in the project root
2. - [ ] Fill in:
   - [ ] `SPREADSHEET_ID` — from your Google Sheet URL
   - [ ] `PERSON_1_NAME` — your name (e.g., "Alice")
   - [ ] `PERSON_2_NAME` — your partner's/roommate's name (e.g., "Bob")
   - [ ] `TELLER_APP_ID` — from your [Teller dashboard](https://teller.io)
   - [ ] `TELLER_ENVIRONMENT` — `sandbox` to test, `development` or `production` for real banks
   - [ ] Leave `TELLER_API_KEY` blank — tokens are saved automatically from the UI

## ✅ Run the App

```bash
docker compose up --build
```

Or in the background:

```bash
docker compose up -d
```

Open **http://localhost:3000**

## ✅ Connect Your Bank (first time)

1. - [ ] Click **🏦 Accounts** in the header
2. - [ ] Click **+ Connect a Bank**
3. - [ ] Complete the Teller Connect popup (sandbox credentials: username `user_good`, password `pass_good`)
4. - [ ] Your account appears in the list with an **Active** badge
5. - [ ] Your access token is saved automatically — no `.env` editing needed

## ✅ Sync & Review Transactions

1. - [ ] Click **⟳ Sync Banks** in the header
2. - [ ] Choose a date range and select which accounts to include (all checked by default)
3. - [ ] Click **Sync** — transactions load into the review table
4. - [ ] Mark shared expenses with the **50/50** toggle, or click **🧮** for a custom split
5. - [ ] Add context with **🗒️** (notes) if needed
6. - [ ] Click **📊 Send to Sheet** — shared transactions go to your Google Sheet

## ✅ Optional: CSV Upload

To import from a CSV bank statement:
1. - [ ] Click **📂 Upload CSV** and select a Discover or Barclays file
2. - [ ] Transactions appear in the review table alongside Teller ones

## ✅ Optional: CSV Auto-Import (watch folder)

```bash
chmod +x run_csv_watcher.sh
./run_csv_watcher.sh
```

Drop CSV files into `csv_imports/` and they'll auto-import. Processed files move to `csv_imports/processed/`.

---

## 🆘 Troubleshooting

**"Connect a Bank" button not visible?**
- Check that `TELLER_APP_ID` is set in `.env` and the backend has been restarted

**Account shows "Connection Error"?**
- Click **↺** on the row to re-authenticate with your bank

**Account shows "Rate Limited"?**
- Teller is temporarily throttling — wait a few minutes and sync again; no action needed

**Google Sheets issues?**
- Confirm `credentials.json` is in `backend/`
- Confirm the sheet is shared with the `client_email` from `credentials.json`
- Run `curl http://localhost:8000/api/gsheet/verify` to diagnose

**Backend logs:**
```bash
docker compose logs backend
```

---

🎉 **You're all set!** Start syncing banks and tracking shared expenses!
