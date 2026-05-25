# Budgets & goals

> Source: `backend/routers/budgets.py`, `backend/routers/goals.py`, `backend/db/models.py`

Two related-but-separate ideas:

- **Budgets** = monthly spending caps (per category)
- **Goals** = savings targets with a deadline

Both feed the dashboard cards, alerts, and the AI advisor's context.

## Budgets

| Field | Notes |
|---|---|
| `category` | Primary key — one budget per category |
| `monthly_limit` | Dollar cap per month |

Computed at read time:

- `current_month_spent` — sum of transactions matching the category in the current month
- `over_budget` — derived flag

When a budget is exceeded, [AlertsCard](../tabs/finances-dashboard.md) surfaces it and the advisor sees it in context.

## Goals

| Field | Notes |
|---|---|
| `kind` | `emergency_fund`, `debt_payoff`, `vacation`, `home`, `custom` |
| `target_amount` | Final number |
| `current_amount` | Either manual or auto-pulled from `linked_account_id` |
| `target_date` | Used to compute monthly required & pace |
| `priority` | Ordering hint |

Computed:

- `progress_pct` = current / target
- `monthly_required` = (target − current) / months remaining
- `pace_status` ∈ {`on_track`, `ahead`, `behind`, `stalled`}

## How they show up

- **Budgets tab** — full table editor.
- **Goals tab** — full editor with kind / priority / link selectors.
- **Dashboard** — `BudgetsCard` and `GoalsCard` summarize current month / pace.
- **Advisor** — sees the full list each turn, can answer "am I on track for X?"
