# Transactions tab

> Source: `frontend/src/App.js`, `frontend/src/components/transactions/*`, `backend/routers/transactions.py`

The home tab. A review queue of every transaction (Teller-synced + CSV-uploaded) where you mark splits, add notes, categorize, and send shared expenses to Google Sheets.

## What you see

| Element | What it does |
|---|---|
| **Sync panel** (top banner) | Shows last sync time and account status. Buttons: **Sync Banks**, **Accounts**. See [Sync panel section below](#sync-panel). |
| **Control bar** | Stats pills (total / shared count / shared amount / unreviewed). Buttons: **📂 Upload CSV**, **📊 Send to Sheet**. |
| **Bulk bar** (only when rows selected) | **Mark personal**, **50/50 split**, **Suggest categories**, **Clear selection**. |
| **Filter bar** | Bank dropdown, month dropdown, split-type dropdown, search box. Shows visible/total count. |
| **Transaction table** | One row per transaction. Inline split toggle, type flip, note + adjust expanders. |

## Common workflows

### Mark a single transaction as a 50/50 shared split

1. Click the **½** pill on the row. The split is saved instantly and the row marks as reviewed.

### Add a custom split

1. Click **🧮** on the row → an inline adjust panel opens below it.
2. Enter how much each person owes, or click **50/50** for a quick equal split.
3. Save.

### Add a note

1. Click **🗒️** → an inline note editor opens.
2. Type, save. The icon becomes **📝** to show a note exists.

### Bulk-mark many rows

1. Tick the checkboxes (or the header checkbox to select all visible).
2. Use **Mark personal** or **50/50 split** in the bulk bar.

### Get AI-suggested categories

1. Select rows.
2. Click **Suggest** → opens the [Suggest Categories preview modal](../modals/suggest-preview.md).
3. Review per-row suggestions and apply.

### Send shared expenses to Google Sheets

1. Click **📊 Send to Sheet** in the control bar.
2. All currently shared transactions are written to the configured Google Sheet and cleared from the queue.

### Upload a CSV

1. Click **📂 Upload CSV** and pick a Discover or Barclays CSV.
2. The [Upload CSV modal](../modals/upload-csv.md) opens for account/balance metadata.
3. Submit → rows appear in the table.

## Sync panel

Shows account-connection health and last sync time. The buttons open:

- **Sync Banks** → [Sync Bank modal](../modals/sync-bank.md)
- **Accounts** → [Linked Accounts modal](../modals/accounts-modal.md)

See also: [Bank sync concept](../concepts/bank-sync.md).

## Under the hood

- Transactions endpoint: `GET /api/transactions/all`
- Single edit: `PUT /api/transactions/{id}`
- Bulk edit: `PUT /api/transactions/bulk`
- Bulk suggest: `POST /api/suggest-categories/bulk`
- Send to Sheet: `POST /api/send-to-gsheet`
