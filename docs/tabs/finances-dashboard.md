# Finances → Dashboard

> Source: `frontend/src/components/finances/DashboardTab.js`, `frontend/src/components/finances/dashboard/useDashboardLayout.js`, `frontend/src/components/finances/cards/*`, `backend/routers/dashboard.py`

The wide view: a greeting with KPIs, then a grid of cards.

For "what should I do today", see [Today](finances-today.md) instead. Dashboard is for looking around; Today is for being told.

## Range selector

A 3M / 6M / 12M toggle changes the window for every card that aggregates — cash flow, income vs. expenses, spending by category.

## The default arrangement is an argument

Cards are ordered as a narrative: **Position → Flow → Trend → Assets → Constraints → Commitments → Signals**. Each card shows its chapter and number in the header, so the argument survives being rearranged — move Budgets above Balances and it still says which part of the story it belongs to.

| # | Card | What it shows | Backend |
|---|---|---|---|
| 01 | **Net worth** | Cash + investments + property equity − debt, and the trend | `GET /api/balances/summary` |
| 02 | **Cash flow** | Money in vs. out for the range | `GET /api/dashboard` |
| 03 | **Spending** | Top categories | `POST /api/insights/spending-summary` |
| 04 | **Income vs. expenses** | Trend chart | `GET /api/dashboard/income-vs-expenses` |
| 05 | **Balances** | Per-account list | `GET /api/balances/summary` |
| 06 | **Portfolio** | Investment value, gain, allocation, top positions | `GET /api/investments/portfolio` |
| 07 | **Credit** | Card utilization — cards only, never mortgages | `GET /api/accounts/credit-health` |
| 08 | **Budgets** | Current-month progress | `GET /api/budgets` |
| 09 | **Goals** | Savings goals and pace | `GET /api/goals` |
| 10 | **Recurring** | Detected subscriptions and bills | `GET /api/bills/upcoming` |
| 11 | **Alerts** | Everything the coach flagged | `GET /api/alerts` |

## Rearranging

**⠿ Arrange cards** turns the grid live: drag to move, pull the bottom-right corner to resize, × to remove. **✓ Done arranging** saves.

Dragging is off by default, and deliberately so. The cards hold charts, buttons and scrollable lists; a grid that's always live turns every stray drag into an accidental rearrangement of a screen you were only reading.

Removed cards come back from the bar at the top while arranging. **Reset to default** restores the narrative order.

Layouts persist to `GET/PUT/DELETE /api/dashboard/layout` and are reconciled on load: a card added since you last saved is appended at the bottom rather than silently omitted, and an id that no longer exists is dropped. Shipping a new card never strands you on an arrangement that hides it.

## Alerts come from the coach

The Alerts card is a flat projection of the same rules that produce [Today](finances-today.md)'s next actions — one rule set, two presentations. See [Next actions](finances-today.md#next-actions) for what fires and why.

## Hide numbers

**🙈 Hide numbers** blurs every monetary figure on the page for shoulder-surfing. The setting persists in `localStorage`.
