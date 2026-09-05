# Plan → Goals

> Source: `frontend/src/components/finances/GoalsSection.js`, `backend/routers/goals.py`

Reached at `/plan/goals`. Track savings goals — emergency fund, vacation, debt payoff, custom.

## Fields per goal

| Field | Notes |
|---|---|
| **Name** | e.g., "Emergency fund", "Hawaii trip" |
| **Kind** | `emergency_fund`, `debt_payoff`, `vacation`, `home`, `custom` |
| **Target amount** | Final savings target |
| **Current amount** | Auto-derived from linked account if set, otherwise editable |
| **Target date** | Used to compute monthly required and pace |
| **Priority** | Influences ordering, and what Fin reaches for first |
| **Linked account** | Optional — pulls current balance from a real account |

## Pace status

The backend computes one of: `on_track`, `ahead`, `behind`, `stalled` — based on time elapsed vs. amount saved. The row shows a coloured pill for this; Fin reads the same field through `get_goal_status`.

## Under the hood

- `GET /api/goals`
- `POST /api/goals`
- `PUT /api/goals/{id}`
- `DELETE /api/goals/{id}`

See also: [Budgets & goals concept](../concepts/budgets-and-goals.md).
