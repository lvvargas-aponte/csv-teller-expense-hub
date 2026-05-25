# Bank sync (Teller)

> Source: `backend/routers/teller.py`, `frontend/src/components/accounts/AccountsModal.js`, `frontend/src/components/accounts/SyncModal.js`

[Teller.io](https://teller.io) is the only supported bank-link provider today. The flow has three pieces.

## 1. Connect (one-time per bank)

User clicks **+ Connect a Bank** → Teller Connect popup runs in the browser → on success, the popup hands an **enrollment + access token** back to the frontend → frontend posts to `POST /api/teller/register-token` → backend persists the token to `TELLER_API_KEY` (comma-separated) and re-reads it.

Tokens are env-var-stored intentionally — easy to inspect and prune.

## 2. Sync (on demand)

User clicks **Sync Banks** → picks a date range and accounts → frontend posts to `POST /api/teller/sync` with `{from, to, account_ids}` → for each enrollment, the backend calls Teller's transactions endpoint, dedups against existing rows, and inserts new ones. A balance snapshot is captured per account for net-worth history.

## 3. Reconnect (when broken)

When a token expires or the user changes their bank password, sync returns a **Connection Error** state for that enrollment. The user clicks **↺** in the Linked Accounts modal → Teller Connect popup runs again → frontend posts to `POST /api/teller/replace-token` → backend swaps the bad token for the new one **without losing transactions**.

## Status states

| State | What it means |
|---|---|
| `active` | Token works |
| `closed` | Account closed at the bank |
| `connection_error` | Token broke — needs re-enrollment |
| `rate_limited` | Teller temporarily throttling — wait |

## mTLS (non-sandbox)

For `development` and `production`, every Teller request requires a mutual-TLS handshake using your Teller-issued certificate + private key (paths set via `TELLER_CERT_PATH` / `TELLER_KEY_PATH`).

## Stale / fake tokens

Old test tokens (`tok_abc…`, `tok_one`, `tok_two`, etc.) cause "zombie" Connection Error rows in the modal. The backend logs a warning at startup. Run `py backend/scripts/prune_tokens.py` for an interactive cleanup.

See also: [Teller setup](../getting-started/teller.md), [Linked Accounts modal](../modals/accounts-modal.md).
