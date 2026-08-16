# Finances → Overview

> Source: `frontend/src/components/finances/BalancesSection.js`, `PayoffPlanner.js`, `SpendingInsights.js`

Three stacked sections: balances, debt payoff planning, and AI spending insights.

## Balances section

Lists every account grouped by type — **Depository** (checking / savings / money market), **Investments**, and **Credit**.

For each account:

- Inline-editable institution, nickname, APR (credit), credit limit, statement / due day
- Live balance from SimpleFIN, or **Manual** badge for hand-entered accounts

Actions:

- **+ Add Account** opens the [Add Account modal](../modals/add-account.md) — for accounts not connected via SimpleFIN.
- **✕** removes a manual account.

Backend: `GET /api/balances/summary`, `POST /api/balances/manual`, `PUT /api/balances/manual/{id}`, `PUT /api/accounts/{id}/details`.

## Payoff Planner

Plan how to pay down credit-card debt.

1. Credit accounts from SimpleFIN pre-fill automatically; add more rows manually if needed.
2. Debts are split into two tables by the **Debt type** set in each row's detail panel:
   - **Cards & unsecured debt** — the payoff queue. Ranked by strategy, numbered, and fed by the extra payment.
   - **Loans & secured debt** (`debt_class = loan`) — tracked and editable, but excluded from the
     simulation. Ranking on APR alone would send the extra payment to a mortgage ahead of a 29% card,
     and a 30-year term would swamp the payoff timeline. Each row shows equity once an asset value is set.
3. Pick a strategy:
   - **Avalanche** — highest APR first (minimizes total interest)
   - **Snowball** — lowest balance first (faster early wins)
4. Optional: enter an extra monthly payment — it goes to the unsecured queue only.
5. Click **Calculate** → per-account payoff date and total interest. With loans on the page the
   headline reads **Cards clear in**, since only the queue was simulated.
6. Click **🤖 Ask AI Advisor** for narrative advice (requires Ollama).

Backend: `POST /api/tools/payoff-plan`, `POST /api/tools/payoff-advice`.

## Spending Insights

Lazy-loaded. Click **✨ Show Insights** to fetch:

- Spending by category for the last 3 months
- Next-month forecast
- AI-written summary
- Action cards (top spenders, savings ratio, recurring charges) — each links into the relevant tab

Requires Ollama. If unavailable, a setup nudge card appears instead.

Backend: `POST /api/insights/spending-summary`, `GET /api/insights/forecast`.
