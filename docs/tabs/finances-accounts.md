# Finances → Accounts

> Source: `frontend/src/components/finances/AccountsTab.js`, `backend/routers/accounts.py`, `backend/routers/credit_health.py`

A focused account view with three sections.

## Accounts summary card

Aggregates total balances across all account types — the same numbers that feed net worth.

## Credit utilization

Per-card table showing:

- Card name + institution
- Balance vs. credit limit
- Utilization % (with color coding: green < 30%, amber 30–70%, red > 70%)
- APR
- Days until statement / due

A summary card at the top shows aggregate utilization across all credit cards.

Backend: `GET /api/accounts/credit-health`.

## Cash list

All depository accounts (checking, savings, money market) grouped by type with inline-editable fields.

- **+ Add** opens the [Add Account modal](../modals/add-account.md).
- **✕** removes a manual account.

Backend: `GET /api/balances/summary`, `PUT /api/accounts/{id}/details`.
