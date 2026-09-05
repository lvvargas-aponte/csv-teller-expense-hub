# Debt

> Source: `frontend/src/components/finances/DebtPage.js`, `PayoffPlanner.js`, `BorrowingPowerPanel.js`, `cards/CreditUtilizationCard.js`, `backend/routers/credit_health.py`, `backend/routers/tools.py`

Everything you owe, what it costs you, and how to clear it. This page absorbed the old
**Finances → Overview** — its balances list moved to [Accounts](accounts.md) and its spending
insights to [Home](home.md).

## Summary bar

| Reading | Notes |
|---|---|
| **Total owed** | Across open cards and loans. A closed card counts toward nothing but keeps its row. |
| **Utilization** | Overall percentage with a status word — *Good* / *Watch* / *High*. The word matters, not just the colour: colour alone does not survive greyscale or colour-blindness. |
| **Next payment due** | The soonest due day among open accounts, with the card's name. |

## Account list

Three sections — **Credit cards**, **Loans**, and **Closed** (collapsed by default).

Cards and installment loans are separated deliberately: a loan has no credit limit to be a percentage
of, and a fixed amortisation schedule rather than a balance you choose how fast to clear.

Each row expands into a **drawer** — the only place in the app where these are set:

- Credit limit
- APR
- Statement day / due day
- Monthly payment (a loan's has to come off a statement; a card's can be worked out from balance + APR)
- Opened-on and closed-on dates

Clearing a closed date reopens the account. Closing or reopening re-fetches the server-side
utilization, since it is computed from the open accounts.

**+ Add credit card or loan** creates a *manual* account. To link one that syncs, go to
[Accounts](accounts.md).

## Credit utilization card

Per-card table: balance vs. limit, utilization percentage with its band, APR, and days until
statement/due. A card with no limit set links straight into that row's drawer with the limit field
focused — and scrolls the row into view, since the card sits below the list.

Backend: `GET /api/accounts/credit-health`.

## Payoff planner

1. Open, non-zero credit cards pre-fill from your accounts. Paid-off cards and installment loans are
   excluded — a mortgage's minimum is not discretionary and its size would swamp every card in the
   ordering.
2. Pick a strategy: **Avalanche** (highest APR first, least total interest) or **Snowball** (smallest
   balance first, faster early wins).
3. Optionally add an extra monthly payment.
4. **Calculate** → per-account payoff date and total interest.
5. **Ask Fin** → a narrative read on the plan. Requires Ollama.

Backend: `POST /api/tools/payoff-plan`, `POST /api/tools/payoff-advice`.

## Borrowing power

What a *lender* reads, as opposed to what a credit score reports.

This panel replaced one framed around FICO's five factors. Only one of those five could be measured
honestly here — payment history needs delinquencies no bank feed carries, length of history and new
credit need an open date on every account, and credit mix is a count nobody can act on. Four of five
rendered as placeholders.

**Debt-to-income** is the trade. No bureau holds an income figure, so it is not a score factor at all
— but it is what actually gates a mortgage, and this app can compute it precisely because it has the
bank feed a credit monitor does not.

- The numerator is your monthly debt payments. Each is labelled with where it came from; one derived
  from balance and APR is marked **estimated** (the common 1%-plus-interest shape — issuers differ:
  Discover bills 2%, Amex carries a $40 floor).
- If any debt has no payment we can read or derive, the panel **refuses to show a ratio** and names
  the accounts instead. A household whose mortgage has no minimum set would otherwise sum to the
  cards that do and report a confident single-digit ratio.
- Bands: comfortable at or below 15%, watch above that, and a hard ceiling at 43%.

The panel does **not** show a credit score, and says so.

Backend: `GET /api/accounts/borrowing-power`.

## Under the hood

- `GET /api/balances/summary` — account list and balances
- `GET /api/accounts/credit-health` — utilization, per card and overall
- `GET /api/accounts/borrowing-power` — debt-to-income and the payment breakdown
- `GET /api/accounts/details`, `PUT /api/accounts/{id}/details` — the drawer's fields
- `POST /api/tools/payoff-plan`, `POST /api/tools/payoff-advice`
