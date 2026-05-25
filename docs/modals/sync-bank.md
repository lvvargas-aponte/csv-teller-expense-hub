# Sync Bank modal

> Source: `frontend/src/components/accounts/SyncModal.js`, `backend/routers/teller.py`

Title: **🏦 Sync Bank Transactions**. Opens from the **Sync Banks** button in the Sync panel.

## Purpose

Pull transactions for a chosen date range from one or more connected Teller accounts.

## Fields

- **Date range presets**: Previous month / This month / Custom (`from` and `to` date pickers)
- **Account checkboxes**: One per connected account; all checked by default

## Submit

Click **Sync** — for each selected account, the backend calls Teller, dedups against existing transactions, and inserts new rows. Results show in a sync toast (counts per account; rate-limit / error states surfaced).

## Under the hood

- `POST /api/teller/sync` with `{from, to, account_ids[]}`

See also: [Bank sync concept](../concepts/bank-sync.md), [Teller setup](../getting-started/teller.md).
