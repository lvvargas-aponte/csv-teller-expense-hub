# Sync Bank modal

> Source: `frontend/src/components/accounts/SyncModal.js`, `backend/routers/simplefin.py`

Title: **🏦 Sync Bank Transactions**. Opens from the **Sync Banks** button in the Sync panel.

## Purpose

Pull transactions for a chosen date range from one or more connected SimpleFIN accounts.

## Fields

- **Date range presets**: Previous month / This month / Custom (`from` and `to` date pickers)
- **Account checkboxes**: One per connected account; all checked by default

## Submit

Click **Sync** — for each stored Access URL, the backend fetches accounts with bundled transactions from SimpleFIN, dedups against existing rows, and inserts new ones. Results show in a sync toast (counts per account; rate-limit / error states surfaced).

## Under the hood

- `POST /api/simplefin/sync` with `{from, to, account_ids[]}`

See also: [Bank sync concept](../concepts/bank-sync.md), [SimpleFIN setup](../getting-started/simplefin.md).
