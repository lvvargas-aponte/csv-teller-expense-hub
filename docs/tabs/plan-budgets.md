# Plan → Budgets

> Source: `frontend/src/components/finances/BudgetsSection.js`, `backend/routers/budgets.py`

Reached at `/plan/budgets`. Set a monthly spending limit per category. Home's **Budgets** card and its **Needs you** feed both read from these.

## What you see

A table of categories with:

- Monthly limit ($)
- Current month's spend
- Progress bar
- Edit / delete actions

## Common actions

- **Add a budget** — pick a category, enter a monthly limit.
- **Edit** — click the limit; save in place.
- **Delete** — removes the budget; spending in that category no longer triggers alerts.

## Under the hood

- `GET /api/budgets` — list with current-month spend
- `PUT /api/budgets/{category}` — upsert a limit
- `DELETE /api/budgets/{category}` — remove

Budget over-runs surface in the [Needs you feed](home.md#needs-you) and are visible to Fin through its `get_budget_status` tool.

See also: [Budgets & goals concept](../concepts/budgets-and-goals.md).
