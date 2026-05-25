# Finances → Dashboard

> Source: `frontend/src/components/finances/DashboardTab.js`, `frontend/src/components/finances/cards/*`, `backend/routers/dashboard.py`

A summary view: a greeting with KPIs and a grid of cards covering net worth, cash flow, spending, balances, budgets, utilization, alerts.

## Range selector

A 3M / 6M / 12M toggle at the top changes the time window for cards that aggregate (cash flow, income vs. expenses, spending by category).

## Cards

| Card | What it shows | Backend |
|---|---|---|
| **NetWorthCard** | Total net worth (cash + investments − credit debt) and recent trend | `GET /api/balances/summary` |
| **CashFlowCard** | Money in vs. out for the selected range | `GET /api/dashboard` |
| **SpendingByCategoryCard** | Top categories with bar/percentage breakdown | `POST /api/insights/spending-summary` |
| **RecurringChargesCard** | Detected subscriptions and recurring bills | `GET /api/bills/upcoming` |
| **BalancesCard** | Per-account balance list | `GET /api/balances/summary` |
| **PortfolioCard** | Total investment value, unrealized gain, allocation, top positions | `GET /api/investments/portfolio` |
| **BudgetsCard** | Budget progress for current month | `GET /api/budgets` |
| **CreditUtilizationCard** | Aggregate credit-card utilization % | `GET /api/accounts/credit-health` |
| **AlertsCard** | Budget warnings and unusual spending | `GET /api/alerts` |
| **IncomeVsExpensesCard** | Trend chart for the selected range | `GET /api/dashboard/income-vs-expenses` |

## Layout / personalization

Card placement is persisted per-user via `GET/PUT /api/dashboard/layout`.

## Tweaks panel

A floating **⚙ Tweaks** button (bottom-right) opens a small panel for:

- Dark mode toggle
- Accent color
- Show/hide projections

Source: `frontend/src/components/finances/TweaksPanel.js`.
