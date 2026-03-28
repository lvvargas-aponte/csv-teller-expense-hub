# Quick Start Checklist

Follow these steps to get csv-teller-expense-hub running:

## ✅ Pre-Setup

- [ ] Clone the repo: `git clone https://github.com/lvvargas-aponte/csv-teller-expense-hub.git`
- [ ] Have Docker installed on your machine

## ✅ Google Cloud Setup (One-time)

1. - [ ] Go to [Google Cloud Console](https://console.cloud.google.com)
2. - [ ] Create a new project (or select existing)
3. - [ ] Enable Google Sheets API
4. - [ ] Create Service Account credentials
5. - [ ] Download JSON key file
6. - [ ] Save it as `credentials.json` in the `backend/` folder

## ✅ Google Sheet Setup

1. - [ ] Create a new Google Sheet
2. - [ ] Add these headers in Row 1:
```
Transaction Date | Description | Amount | Who | What | [YOUR_NAME] Owes | [PARTNER_NAME] Owes | Notes
```
Replace `[YOUR_NAME]` and `[PARTNER_NAME]` with actual names (e.g., "Alice Owes | Bob Owes")
3. - [ ] Copy the Sheet ID from the URL (between `/d/` and `/edit`)
4. - [ ] **IMPORTANT:** Share the sheet with your service account email
- Find the email in `credentials.json` under `client_email`
- Click "Share" in Google Sheets
- Paste the service account email
- Give it "Editor" permissions

## ✅ Configure Environment

1. - [ ] Copy `.env.example` to `.env` in the `backend/` folder
2. - [ ] Edit `.env` and fill in:
- [ ] `SPREADSHEET_ID` - from your Google Sheet URL
- [ ] `PERSON_1_NAME` - your name (e.g., "Alice")
- [ ] `PERSON_2_NAME` - your partner's/roommate's name (e.g., "Bob")
- [ ] `TELLER_API_KEY` and `TELLER_APP_ID` (optional, for Teller.io integration)

## ✅ Run the App

```bash
# Start everything with Docker
docker-compose up --build

# Or run in background
docker-compose up -d
```

## ✅ Verify It's Working

1. - [ ] Open browser to http://localhost:3000
2. - [ ] Click "Upload CSV" and test with a bank statement
3. - [ ] Mark a transaction as shared (click "50/50")
4. - [ ] Click "📊 Send to GSheet"
5. - [ ] Check your Google Sheet - the transaction should appear!

## ✅ Optional: CSV Auto-Import

If you want to auto-process CSV files dropped into a folder:

```bash
chmod +x run_csv_watcher.sh
./run_csv_watcher.sh
```

Now drop CSV files into `csv_imports/` folder and they'll auto-import!

---

## 🆘 Troubleshooting

**"Failed to authenticate with Google"**
- Make sure `credentials.json` is in the `backend/` folder
- Verify you shared the Google Sheet with the service account email

**"Headers don't match"**
- Check your Google Sheet headers match exactly: `Transaction Date | Description | Amount | Who | What | [PERSON_1_NAME] Owes | [PERSON_2_NAME] Owes | Notes`
- The names must match what's in your `.env` file

**"No transactions appearing"**
- Check backend logs: `docker-compose logs backend`
- Verify CSV format (supports Discover and Barclays)

---

🎉 **You're all set!** Start uploading bank statements and tracking shared expenses!