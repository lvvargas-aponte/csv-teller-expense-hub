# Finances → Loans

> Source: `frontend/src/components/finances/LoansPage.js`, `frontend/src/components/finances/loans/*`, `backend/amortization.py`, `backend/routers/loans.py`

Mortgages, auto loans, HELOCs — and the answer to "how much of that payment was interest?"

## What you see

Four KPIs (total debt, monthly payments, equity in secured assets, loan count), then one expandable row per loan. Expanding opens the amortization view.

## This month's payment

The headline of every loan:

```
Payment #79   P&I $1,111.48 + $650.00 escrow
  interest    $650.40
  principal   $461.08
  balance     $207,666.17
  tenants have paid down $32,333.83 of principal
```

Cumulative principal paid is the number that makes the buy-and-hold thesis concrete: on a rental, it's how much of the house the rent has bought so far.

## Schedule

A stacked bar of principal against interest across the whole term — watching interest give way to principal is what makes amortization legible — plus a paginated table (60 payments a page; a 360-row table is unreadable).

## What-if

Enter an extra monthly amount and see months and interest saved. On a $240,000 mortgage at 3.75%, an extra $300/month pays it off 9 years 9 months early and saves $57,266.

## Fields worth understanding

| Field | Notes |
|---|---|
| **Principal & interest** | Leave blank to derive it from amount, rate and term |
| **Escrow** | Taxes and insurance. Deliberately separate — it doesn't pay down principal, and property economics already counts it as an operating expense |
| **Current balance** | Optional. Left blank, the balance is computed from the payment schedule |
| **Lien position** | 1 = first mortgage, 2 = HELOC/second. Needed for CLTV |
| **Secured by** | Links the loan to a property. Leave empty for auto/student/personal |

## How the balance is resolved

In precedence order:

1. A **linked account** — refreshed by sync, so it's freshest
2. **Current balance**, if you supplied one
3. The **amortized balance** implied by the schedule
4. Original principal, only when the loan can't be placed on a schedule

Step 3 matters: for a hand-entered loan it's the only figure reflecting payments already made. Using original principal instead understates equity by every dollar of principal paid to date — tens of thousands on an established mortgage.

Asset value resolves similarly: the linked property's valuation wins, `account_details.asset_value` is the fallback that keeps auto loans working, and it returns nothing rather than guessing.

## Under the hood

- `GET/POST/PUT/DELETE /api/loans[/{id}]`
- `GET /api/loans/{id}/current-payment` — the interest/principal split
- `GET /api/loans/{id}/schedule` — paginated amortization
- `POST /api/loans/{id}/what-if` — extra-payment comparison

See also: [Properties](finances-properties.md), [Debt Payoff](finances-overview.md#payoff-planner).
