# Bank sync (SimpleFIN)

> Source: `backend/simplefin.py`, `backend/routers/simplefin.py`, `frontend/src/components/accounts/AccountsModal.js`, `frontend/src/components/accounts/SyncModal.js`

[SimpleFIN](https://www.simplefin.org) is the only supported bank-link provider. The flow has three pieces.

## 1. Connect (one-time per bank)

User visits [bridge.simplefin.org/simplefin/create](https://bridge.simplefin.org/simplefin/create) externally, links their bank there, and gets a one-time-use **Setup Token**. Back in the app, they paste the token into **Linked Accounts** → **Connect via SimpleFIN** and click **Connect** → frontend posts to `POST /api/simplefin/claim` → the backend exchanges the token once for a durable **Access URL** and appends it to `SIMPLEFIN_ACCESS_URLS` (comma-separated) in `.env`.

Access URLs are env-var-stored intentionally — easy to inspect and prune.

## 2. Sync (on demand)

User clicks **Sync Banks** → picks a date range and accounts → frontend posts to `POST /api/simplefin/sync` with `{from, to, account_ids}` → for each stored Access URL, the backend fetches accounts with bundled transactions (`/accounts`), dedups against existing rows, and inserts new ones. A balance snapshot is captured per account for net-worth history.

Because SimpleFIN bundles balances and transactions into one response per Access URL, a sync is a single request per connection rather than one call per account.

## 3. Disconnect

There's no per-account revoke — one Access URL covers every account from that Bridge session. Clicking **Disconnect** on a single account hides it locally (skipped on every future sync/listing) without touching the rest of the connection; **Delete permanently** removes that hide. To drop an entire connection (all accounts under one Setup Token), use `DELETE /api/simplefin/connections`.

## Rate limits

SimpleFIN asks clients to stay under ~24 requests/day per Access URL — fine for manual or occasional scheduled syncs, not for polling.

See also: [SimpleFIN setup](../getting-started/simplefin.md), [Linked Accounts modal](../modals/accounts-modal.md).
