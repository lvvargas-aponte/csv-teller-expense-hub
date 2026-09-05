# Accounts

> Source: `frontend/src/components/finances/AccountsTab.js`, `accounts/*`, `backend/routers/accounts.py`, `backend/routers/balances.py`

The answer to **"what is linked, and is it healthy?"** — every account the app knows about, in one
list, whether it syncs or you keep it by hand.

## Page actions

| Button | What it does |
|---|---|
| **↺ Sync all** | Re-pulls every connected bank and brokerage at once. |
| **+ Add account** | Opens the [Add Account modal](../modals/add-account.md). This adds a **manual** account — the balance is whatever you type and nothing updates it. |

The note under the buttons says the same thing, because on a page about connected accounts a big
primary button reads as "link a bank" when it is not. Linking a real bank is the **Connections
strip** immediately below.

## Connections strip

One chip per connected institution, with its last-sync time. A chip turns red and says
*needs reconnect* when SimpleFIN or SnapTrade has lost authorisation. From here you can:

- Connect a new bank — see [SimpleFIN setup](../getting-started/simplefin.md)
- Connect a brokerage — see [SnapTrade setup](../getting-started/snaptrade.md)
- Re-run a broken connection

## Account sections

Four collapsible sections, each with a count and a subtotal:

| Section | Contents | Editable here? |
|---|---|---|
| **Credit cards & loans** | Every revolving card and installment loan | Read-only — the drawer that sets limit, APR, statement and due day lives on [Debt](debt.md) |
| **Cash & savings** | Checking, savings, money market | Yes — inline nickname, institution and balance |
| **Investments** | Brokerage and retirement accounts | Read-only — positions live on [Invest](invest.md) |
| **Property & vehicles** | Manual real assets that count toward net worth | Yes — you set the value; nothing updates it |

Bucketing is done by `utils/accountBucket.js` against the server's subtype vocabulary
(`GET /api/accounts/metadata`), which arrives after first paint — the lists re-bucket when it lands.

Every row shows a **Manual** badge when the balance is hand-entered, and the live balance plus its
cache timestamp when it is synced.

## Under the hood

- `GET /api/balances/summary` — the account list, connections and net-worth rollup
- `GET /api/accounts/details` — limit / APR / statement metadata for every account
- `PUT /api/balances/{account_id}` — edit a balance
- `POST /api/balances/manual`, `DELETE /api/balances/manual/{id}` — manual accounts
- `PUT /api/accounts/{id}/details` — account metadata
- `GET /api/accounts/metadata` — the subtype vocabulary used for bucketing

See also: [Bank sync concept](../concepts/bank-sync.md), [Debt](debt.md).
