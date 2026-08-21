# Finances → Accounts

> Source: `frontend/src/components/finances/AccountsTab.js`, `backend/routers/balances.py`, `backend/routers/credit_health.py`

The roster of every account you hold. Each account appears exactly once, in one
of three groups.

Net worth is **not** on this page — see [Finances → Net Worth](finances-net-worth.md).
Accounts previously carried a net-worth banner *and* a right-rail card that
computed its own, smaller figure from cash minus debt; the two disagreed on
every household with a mortgage or a brokerage account.

## Groups

Accounts are bucketed by `frontend/src/utils/accountType.js`, which mirrors the
backend's `analytics._classify_account_bucket`. Both use the same rule, so each
group heading's total matches the figure the summary reports.

| Group | Contents | Heading total |
|---|---|---|
| **Credit Cards & Loans** | `type = credit` | `total_credit_debt` |
| **Cash & Savings** | `type = depository`, excluding investment subtypes | `total_cash` |
| **Investments & Retirement** | `type = investment`, **or** a recognized subtype (`401k`, `ira`, `hsa`, `brokerage`, …) on any account | `total_investments` |

That last rule is why a 401(k) you entered as a depository account files under
Investments: the backend already counts it as an investment, so listing it as
cash would put the page at odds with its own totals.

## Credit Cards & Loans

Per-card table with inline-editable cells — APR, credit limit, minimum payment,
statement day, due day. Edits save as you leave the cell. Also shows utilization
(green < 30%, amber 30–70%, red > 70%) and a countdown when a due date is within
a week.

## Cash & Savings / Investments & Retirement

Balance rows showing institution, live-or-manual sync state, and balance. Manual
accounts carry **✎** (edit balance) and **✕** (remove) on hover.

## Right rail

- **On this page** — cash, investments, owed, available credit, and the next
  minimum payment due. These are this page's own totals, not net worth; a link
  at the bottom goes to the full figure.
- **Credit Utilization** — per-card bars plus an aggregate. Loans and
  limit-less cards are excluded, since utilization needs a limit.

## Adding accounts

**+ Add** at the foot of each list opens the
[Add Account modal](../modals/add-account.md) with the matching preset.

Backend: `GET /api/balances/summary`, `POST /api/balances/manual`,
`PUT /api/balances/{id}`, `DELETE /api/balances/manual/{id}`,
`GET|PUT /api/accounts/{id}/details`.
