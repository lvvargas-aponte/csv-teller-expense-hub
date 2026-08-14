# Add Account modal

> Source: `frontend/src/components/finances/BalancesSection.js`, `frontend/src/components/finances/AccountsTab.js`, `backend/routers/balances.py`

Opens from **+ Add Account** in the Balances section (Overview tab) or the cash list (Accounts tab).

## Purpose

Track an account that **isn't connected via SimpleFIN** — typically:

- A 401(k) / brokerage you only check manually
- An old savings account you don't want to enroll
- Cash on hand

These show a **Manual** badge and survive restarts.

## Fields

| Field | Notes |
|---|---|
| **Type** | `depository` (checking/savings) or `credit` (credit card) |
| **Institution** | Bank / brokerage name |
| **Nickname** | Free text; shown in lists |
| **Balance** | Current balance — for credit cards, enter as a **positive number** for amount owed |
| **APR** (credit only) | Used by the [Payoff Planner](../tabs/finances-overview.md#payoff-planner) |
| **Credit limit** (credit only) | Drives utilization % |

## Updating

Manual balances are inline-editable in the Balances section. Edits are saved immediately.

## Under the hood

- `POST /api/balances/manual`
- `PUT /api/balances/manual/{id}`
- `DELETE /api/balances/manual/{id}`
