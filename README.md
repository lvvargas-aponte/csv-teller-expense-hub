# Bank Statement & Shared Expense Tracker - Setup Guide

## 🎯 Overview
This app helps you:
- Pull transactions from Teller.io (auto-connected banks)
- Auto-import CSV files from Discover & Barclays
- Review and mark shared expenses
- Send approved expenses directly to Google Sheets

## 📋 Prerequisites

1. **Google Cloud Service Account**
   - Go to [Google Cloud Console](https://console.cloud.google.com)
   - Create a new project or select existing
   - Enable Google Sheets API
   - Create Service Account credentials
   - Download JSON key file as `credentials.json`
   - Share your Google Sheet with the service account email

2. **Teller.io Account**
   - Sign up at [Teller.io](https://teller.io)
   - Get your Application ID and Private Key

3. **Google Sheet Setup**
   - Create a Google Sheet with these headers (using YOUR names):
     `Transaction Date | Description | Amount | Who | What | [PERSON_1_NAME] Owes | [PERSON_2_NAME] Owes | Notes`
   - Example: If you set `PERSON_1_NAME=Alice` and `PERSON_2_NAME=Bob`, your headers should be:
     `Transaction Date | Description | Amount | Who | What | Alice Owes | Bob Owes | Notes`
   - Copy the Sheet ID from the URL (the long string between `/d/` and `/edit`)

## 🚀 Installation

### 1. Clone and Setup

```bash
git clone https://github.com/lvvargas-aponte/csv-teller-expense-hub.git
cd csv-teller-expense-hub
```

### 2. Setup Google Credentials

Download your service account JSON from Google Cloud Console and save it as `credentials.json` in the backend folder.

**Important:** Make sure to share your Google Sheet with the service account email (found in credentials.json as `client_email`)

### 3. Configure Environment

Create `.env` file in the backend folder (see example above). **Customize the person names** to match your household!

### 1. Environment Variables

Create a `.env` file in the backend folder:

```bash
# Teller API Configuration
TELLER_ENVIRONMENT=development
TELLER_API_KEY=your_teller_api_key
TELLER_APP_ID=your_app_id
TELLER_CERT_PATH=path/to/certificate.pem
TELLER_KEY_PATH=path/to/private_key.pem

# Google Sheets Configuration
SPREADSHEET_ID=your_google_sheet_id
SHEET_NAME=Sheet1  # Optional: name of the tab in your Google Sheet

# Person Names (customize for your household/roommates)
PERSON_1_NAME=Alice
PERSON_2_NAME=Bob

# CSV Watch Folder
CSV_WATCH_FOLDER=./csv_imports
```

**Customize Person Names:**
- Replace `Alice` and `Bob` with your actual names
- These will appear in the Google Sheet headers (e.g., "Alice Owes", "Bob Owes")
- This makes the app shareable - anyone can use their own names!

### 3. Build and Run with Docker

```bash
# Build and start all services
docker-compose up --build

# Or run in detached mode
docker-compose up -d
```

### 4. Start CSV Watcher (Optional)

In a separate terminal:

```bash
# Make script executable
chmod +x run_csv_watcher.sh

# Run the watcher
./run_csv_watcher.sh
```

## 📂 Project Structure

```
.
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── csv_parser.py
│   ├── gsheet_integration.py
│   ├── csv_watcher.py
│   ├── credentials.json  # Add this
│   └── .env  # Add this
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       └── App.js
└── csv_imports/  # Created automatically
    ├── processed/  # Successfully imported files
    └── failed/     # Failed imports
```

## 🔄 Workflow

### Option 1: Manual CSV Upload
1. Open app at http://localhost:3000
2. Click "Upload CSV"
3. Select Discover or Barclays CSV file
4. Transactions appear in review table

### Option 2: Auto-Import (Watch Folder)
1. Start the CSV watcher script
2. Drop CSV files into `csv_imports/` folder
3. Files are automatically processed
4. Successful files move to `csv_imports/processed/`
5. Failed files move to `csv_imports/failed/` with error logs

### Option 3: Teller.io (Auto-fetch)
1. Click "Connect Account" in the app
2. Complete Teller authentication flow
3. Select accounts to import
4. Transactions automatically populate

### Review & Send
1. Review all transactions in the table
2. Click "50/50" for equal split, or "Edit" for custom split
3. Fill in Who/What/Notes as needed
4. Click "📊 Send to GSheet" when ready
5. Transactions are sent to your Google Sheet and cleared from review

## 🛠️ Testing

### Verify Google Sheet Connection
```bash
curl http://localhost:8000/api/gsheet/verify
```

### Test CSV Upload
```bash
curl -X POST http://localhost:8000/api/upload-csv \
  -F "file=@your_statement.csv"
```

## 🐳 Kubernetes Deployment

Coming soon! The app is containerized and ready for k8s deployment.

## 🔍 Troubleshooting

**Google Sheets not working?**
- Make sure you shared the sheet with the service account email (found in your credentials JSON as `client_email`)
- Verify SPREADSHEET_ID is correct (from the URL between `/d/` and `/edit`)
- Check that credentials.json is in the backend folder
- Test with: `curl http://localhost:8000/api/gsheet/verify`

**CSV files not processing?**
- Check backend logs: `docker-compose logs backend`
- Verify CSV format matches Discover/Barclays structure
- Check `csv_imports/failed/` folder for error logs

**Teller.io not connecting?**
- Verify TELLER_APPLICATION_ID and TELLER_PRIVATE_KEY
- Check if using correct environment (sandbox vs production)

## 📝 Notes

- In-memory storage: Transactions exist only until sent to Google Sheet
- No database needed - this is a review-and-send workflow
- CSV watcher processes files one at a time
- Teller.io transactions merge with CSV transactions in one view