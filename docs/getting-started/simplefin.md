# SimpleFIN (bank sync)

> Source: `backend/simplefin.py`, `backend/routers/simplefin.py`, `frontend/src/components/accounts/AccountsModal.js`

[SimpleFIN](https://www.simplefin.org) is a flat-fee bank/credit-card aggregator ($1.50/mo, billed directly to you, not per-connection) — an alternative to [Teller](teller.md) with much broader institution coverage, since it's built for personal-finance apps rather than multi-tenant fintech products. It powers the same **Sync Banks** and **Linked Accounts** flows Teller does; both sources can be connected at once.

## One-time setup

1. Go to [bridge.simplefin.org/simplefin/create](https://bridge.simplefin.org/simplefin/create) and connect one or more banks in the browser.
2. Generate a **Setup Token** — a one-time-use blob (base64 of a claim URL).
3. In the app, open **Linked Accounts** → **Connect via SimpleFIN**, paste the Setup Token, and click **Connect**.
4. The backend claims the token immediately (a Setup Token can only be claimed once) and saves the resulting **Access URL** to `SIMPLEFIN_ACCESS_URLS` in `.env`. Leave that variable blank yourself — it's written automatically, the same way `TELLER_API_KEY` is.
5. Run a **Sync** to pull in accounts and transactions.

## What SimpleFIN does differently from Teller

- **No app credentials.** There's no `SIMPLEFIN_APP_ID`/environment to configure — the Setup Token *is* the connection.
- **Transactions are bundled.** One `/accounts` fetch returns balances and transactions together, so a SimpleFIN sync is a single request per Access URL instead of one call per account.
- **No account type field.** SimpleFIN's protocol doesn't classify accounts as checking/savings/credit the way Teller does. The backend guesses from the account/institution name (`simplefin.infer_account_bucket`) — e.g. "Amex Platinum" → credit. Double-check the classification after your first sync (it drives whether the balance counts as cash or debt in net worth); correct a wrong balance sign via the existing manual balance-override on that account.
- **No per-account disconnect.** One Access URL covers every account from that Bridge session — there's no API call to revoke just one. Clicking **Disconnect** on a single SimpleFIN account hides it locally (skipped on every future sync/listing) without touching the others; **Delete permanently** removes that hide, so the account reappears on the next sync. To drop an entire connection (all accounts under one Setup Token), use `DELETE /api/simplefin/connections`.
- **Rate limits.** SimpleFIN asks clients to stay under ~24 requests/day per Access URL — fine for manual or occasional scheduled syncs, not for polling.

## Running both Teller and SimpleFIN

Nothing forces a choice — `/api/accounts`, `/api/balances/summary`, and the **Sync Banks** button all merge both sources automatically. If you're migrating off Teller, just stop reconnecting expired Teller tokens; existing SimpleFIN-synced data is unaffected either way.

See also: [Teller (bank sync)](teller.md), [Bank sync concept](../concepts/bank-sync.md).
