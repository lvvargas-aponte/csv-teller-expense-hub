# Add Account modal

> Source: `frontend/src/components/finances/accounts/AddAccountModal.js`, `frontend/src/components/finances/AccountsTab.js`, `backend/routers/balances.py`

Opens from the **+ Add** row at the foot of any list on the [Accounts](../tabs/finances-accounts.md) page. Which list you click from picks the preset.

## Purpose

Track an account that **isn't connected via SimpleFIN** — typically:

- A 401(k) / brokerage you only check manually
- An old savings account you don't want to enroll
- Cash on hand

These show a **Manual** badge and survive restarts.

## Fields

| Field | Notes |
|---|---|
| **Type** | Set by the preset — `credit`, `depository`, or `investment` |
| **Institution** | Bank / brokerage name |
| **Nickname** | Free text; shown in lists |
| **Balance** | Current balance — for credit cards, enter as a **positive number** for amount owed |
| **APR** (credit only) | Used by the [Payoff Planner](../tabs/finances-overview.md#payoff-planner) |
| **Credit limit** (credit only) | Drives utilization % |

The investment preset asks for a single **Current Value**, written to both the
available and ledger fields — the same convention SnapTrade snapshots use. There
is no cost-basis field to put a second number in.

## Updating

Manual accounts carry **✎** (edit balance) and **✕** (remove) on their row in
[Accounts](../tabs/finances-accounts.md). Saving an edit records a balance
snapshot, so your net-worth history keeps the change.

## Under the hood

- `POST /api/balances/manual`
- `PUT /api/balances/manual/{id}`
- `DELETE /api/balances/manual/{id}`
