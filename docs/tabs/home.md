# Home

> Source: `frontend/src/components/finances/DashboardTab.js`, `BalanceSheetHero.js`, `NeedsYouFeed.js`, `cards/*`, `backend/routers/dashboard.py`

The landing page at `/`. It answers two questions in order: **where do we stand**, and **what needs me today**.

This page was rebuilt — it used to be a twelve-card grid under a gradient greeting banner and four KPI
tiles. The banner and tiles are gone; the grid is now six cards in two columns.

## Top bar

| Control | What it does |
|---|---|
| **Hide numbers / Show numbers** | Blurs every currency figure on the page, for screen-sharing. The choice persists in `localStorage` (`eh.blurSensitive`). |
| **3M / 6M / 12M** | The window for the cards that aggregate over time — Cash Flow and Spending by Category. It is a filter group, not a tab strip. |

## Balance-sheet hero

One figure — **net worth** — with the composition that produced it shown to scale as a bar, plus a
row of readings beside it:

| Reading | Source |
|---|---|
| **Health score** | `GET /api/health/score`, with a popover listing which signals were available |
| **Runway** | Months of expenses covered by cash, from `GET /api/health/ratios` |
| **Utilization** | Overall credit-card utilization, from `GET /api/accounts/credit-health` |

The composition bar exists because a negative net worth reads as a catastrophe until you can see that
a mortgage is most of the debt behind it. Property and vehicles count toward the total and are called
out separately — the runway figure deliberately ignores them.

If `Show after-tax net worth` is enabled in [Settings](settings.md), a second line shows the
after-tax figure from `GET /api/tax/after-tax-net-worth`.

## Stale-sync notice

If nothing has synced since last month, the page says so explicitly rather than letting the
month-over-month comparison report a 100% drop in spending.

## Cards

Six cards in two regions — a main column and a narrower side column.

| Card | Column | What it shows | Backend |
|---|---|---|---|
| **Needs you** | main | Ranked feed of what wants a decision: alerts, the weekly digest, unreviewed transactions, missing account metadata. Five visible, the rest one click away. | `GET /api/alerts`, `GET /api/digest/latest`, `GET /api/transactions/all`, `GET /api/accounts/details` |
| **Net worth** | main | Total and trend, with the after-tax line when enabled | `GET /api/dashboard`, `GET /api/balances/summary` |
| **Spending by category** | main | Top categories for the selected range | `GET /api/dashboard` |
| **Budgets** | main | Current-month budget progress | `GET /api/budgets` |
| **Upcoming bills** | side | What is due soon, per card | `GET /api/bills/upcoming` |
| **Cash flow** | side | Money in vs. out, with the outlook and income-vs-expenses trend folded in | `GET /api/dashboard` |

The two columns stack independently rather than sharing grid rows — Cash Flow is by far the tallest
card, and in a shared grid it held its row open and left a hole beside it.

## Needs you

The feed is built client-side by `utils/insightBuilder.js` from four sources at once, then **ranked**
— an over-budget alert outranks a nudge to categorise last week's coffee. Each item carries an action
that navigates to the page that can resolve it; an item that would link to the page you are already on
renders without the link.

Reading the feed marks the current weekly digest as read (`POST /api/digest/{id}/read`).

## What moved away from here

- **Portfolio, allocation, holdings** → [Invest](invest.md)
- **Credit utilization table, payoff planner** → [Debt](debt.md)
- **Recurring charges, bills detail** → [Plan → Commitments](plan-commitments.md)
- **Per-account balance list** → [Accounts](accounts.md)
- **Dark mode and help** → the sidebar footer

!!! note "Card layout is fixed"
    The old drag-to-rearrange grid and its **⚙ Tweaks** panel were removed with the rebuild. The
    `/api/dashboard/layout` endpoints still exist but nothing on Home reads them.
