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

## ✅ Optional: Ollama (AI features)

Ollama powers three features in the app:
- **Spending Insights** — natural-language summary of your monthly spending on the Finances page
- **AI Advisor (one-shot)** — personalized payoff advice in the Debt Payoff Planner
- **Virtual Advisor (chat)** — a multi-turn chat that sees your transactions, balances, and shared splits (Finances → **🤖 Advisor** tab)

The app runs fine without Ollama. When Ollama isn't detected, those sections show a setup nudge instead of an error.

### Install Ollama

**macOS / Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Windows:**
Download and run the installer from [https://ollama.com/download](https://ollama.com/download).  
After installation, `ollama` will be available in your terminal (PowerShell or Command Prompt).

### Pull a model

The default is **`qwen2.5:14b-instruct`** — a strong open-weight model that handles numeric/finance reasoning well. It needs ~9–10 GB VRAM quantized (RTX 3060 12GB / 4070 / 4080 and up). Pull it with:

```bash
ollama pull qwen2.5:14b-instruct
```

**Pick a smaller model if you don't have a GPU or want faster turns.** All of these work with the app:

| Model | Command | Size | Best for |
|---|---|---|---|
| `qwen2.5:14b-instruct` (default) | `ollama pull qwen2.5:14b-instruct` | ~9 GB VRAM | Best quality advisor on moderate GPU |
| `qwen2.5:7b-instruct` | `ollama pull qwen2.5:7b-instruct` | ~5 GB VRAM | Strong, lighter |
| `llama3.1:8b-instruct` | `ollama pull llama3.1:8b-instruct` | ~5 GB VRAM | Proven baseline |
| `llama3.2:3b` | `ollama pull llama3.2:3b` | ~2 GB (CPU-friendly) | Low-spec fallback |

Override the model per deployment via env vars:

```bash
# In .env — picks up on next backend start
OLLAMA_MODEL=qwen2.5:7b-instruct        # used by insights and payoff-advice
OLLAMA_CHAT_MODEL=qwen2.5:14b-instruct  # used by the chat advisor (defaults to OLLAMA_MODEL)
```

### Start the server

```bash
ollama serve
```

Ollama listens on `http://localhost:11434` by default. Leave this terminal open while using the app, or run it in the background:

```bash
# macOS / Linux — background
nohup ollama serve &

# Windows — background (PowerShell)
Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
```

> **macOS note:** the installer registers a system service that starts automatically on login. You may not need to run `ollama serve` manually — check with `ollama list`.

### Verify it's working

```bash
ollama list
# should show your pulled model, e.g.: qwen2.5:14b-instruct   ...   <size>
```

Or ping the server directly:

```bash
curl http://localhost:11434/api/tags
```

Once `ollama serve` is running with a compatible model pulled, the AI features activate automatically the next time you open the app — no config changes needed.

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

**AI features show "Ollama not running" or a setup nudge?**
- Make sure the server is up: `ollama serve`
- Make sure the model is pulled: `ollama pull qwen2.5:14b-instruct` (or whichever you set via `OLLAMA_MODEL`)
- Verify the server responds: `curl http://localhost:11434/api/tags`
- On macOS, the service may already be running — check with `ollama list`
- Confirm `ollama list` output shows exactly the name you put in `OLLAMA_MODEL` / `OLLAMA_CHAT_MODEL`

**Backend logs:**
```bash
docker compose logs backend
```

---

🎉 **You're all set!** Start syncing banks and tracking shared expenses!
