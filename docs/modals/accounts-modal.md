# Linked Accounts modal

> Source: `frontend/src/components/accounts/AccountsModal.js`, `backend/routers/teller.py`

Title: **Linked Bank Accounts**. Opens from the **Accounts** button in the Sync panel.

## Purpose

Connect, reconnect, and disconnect bank accounts via the Teller Connect popup.

## Status badges

| Badge | Meaning |
|---|---|
| **Active** | Token works, syncs succeed |
| **Closed** | Account closed at the bank |
| **Connection Error** | Token broke (password change, MFA reset). Click **↺** to re-enroll |
| **Rate Limited** | Teller is throttling. Wait a few minutes — token is still valid |

## Actions

- **+ Connect a Bank** — opens the Teller Connect popup. On success, the new token is registered and saved to `TELLER_API_KEY`.
- **↺ Reconnect** — replaces a broken token without losing the account's transactions.
- **🗑️ Disconnect** — removes the token; transactions stay in the database. Use cautiously.

## Sandbox testing

In `TELLER_ENVIRONMENT=sandbox` the Connect popup accepts:

- Username: `user_good`
- Password: `pass_good`

## Under the hood

- `POST /api/teller/register-token`
- `POST /api/teller/replace-token`
- `GET /api/accounts`
- `DELETE /api/accounts/{id}`

See also: [Teller setup](../getting-started/teller.md), [Bank sync concept](../concepts/bank-sync.md).
