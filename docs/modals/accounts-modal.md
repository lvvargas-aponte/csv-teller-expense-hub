# Linked Accounts modal

> Source: `frontend/src/components/accounts/AccountsModal.js`, `backend/routers/simplefin.py`

Title: **Linked Bank Accounts**. Opens from the **Accounts** button in the Sync panel.

## Purpose

Connect and disconnect bank accounts via SimpleFIN.

## Connecting a bank

1. Visit [bridge.simplefin.org/simplefin/create](https://bridge.simplefin.org/simplefin/create) externally and link your bank(s) there.
2. Generate a **Setup Token**.
3. Back in the modal, paste it into **Connect via SimpleFIN** and click **Connect**.

The backend exchanges the Setup Token once for a durable Access URL and saves it to `SIMPLEFIN_ACCESS_URLS`.

## Actions

- **Connect via SimpleFIN** — paste a Setup Token to add a new connection.
- **🗑️ Disconnect** — hides an individual account locally; it's skipped on future syncs/listings but its transactions stay in the database. **Delete permanently** un-hides it (it reappears on the next sync).
- To drop an entire connection (all accounts under one Setup Token), remove it via `DELETE /api/simplefin/connections`.

## Under the hood

- `POST /api/simplefin/claim`
- `DELETE /api/simplefin/connections?access_url_masked=...`
- `GET /api/accounts`
- `DELETE /api/accounts/{id}`

See also: [SimpleFIN setup](../getting-started/simplefin.md), [Bank sync concept](../concepts/bank-sync.md).
