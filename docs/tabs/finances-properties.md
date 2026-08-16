# Finances → Properties

> Source: `frontend/src/components/finances/PropertiesPage.js`, `frontend/src/components/finances/properties/*`, `backend/properties.py`, `backend/routers/properties.py`

Real-estate holdings, their rental economics, and how much of each mortgage the tenants have paid off.

## Portfolio header

Four KPIs across every property:

| KPI | Meaning |
|---|---|
| **Portfolio value** | Sum of the latest recorded value per property |
| **Equity** | Value minus outstanding loan balances |
| **Monthly cash flow** | Net operating income minus debt service |
| **Principal paid down** | How much of your mortgages the rent has retired so far |

Any property rated *underperforming* is called out in a banner above the grid, with the quantified reason.

## Property card

Each card shows an equity bar (owned share of current value), the performance pill, and four metrics: cash flow, NOI, cap rate, DSCR. Cards are suppressed from showing an equity bar when no valuation is on file, rather than rendering a misleading 0%.

## Detail view

Walks the full economic chain so the numbers read as an argument rather than a dump:

```
gross scheduled rent
 − vacancy allowance
 = effective gross income
 − operating expenses
 = NOI                    ← excludes the mortgage
 − debt service           ← principal & interest only
 = cash flow
```

Two lines carry tooltips because they're the ones commonly got wrong:

- **NOI excludes debt service.** It measures the property, not the financing. Fold the mortgage in and a cash purchase looks identical to a leveraged one, and cap rate stops being comparable.
- **Escrow is already in operating expenses.** Escrowed taxes and insurance arrive bundled in the mortgage payment, but they're counted once in the expense model. Adding them to debt service would charge the property twice.

Alongside: current value, debt, equity, LTV, cap rate, cash-on-cash, DSCR, and principal paid down.

## Pro forma vs. actuals

A property has an honest **pro forma** from the moment it's created, projected from its configured rent and expenses. Once transactions are tagged to it, an **actual** block is computed alongside.

The two are never blended. A `basis` field names which produced the headline figures — `pro_forma` until six months of tagged history exist, then `actual`. Six months is enough to absorb a quarterly insurance bill and one maintenance surprise.

## Performance rating

`strong` / `watch` / `underperforming`, from deterministic thresholds:

| Trigger | Rating |
|---|---|
| Negative cash flow in 3+ of the last 6 months | underperforming |
| DSCR below 1.0 | underperforming |
| DSCR 1.0–1.25 (the lender comfort threshold) | watch |
| Operating expenses above 55% of effective gross income | watch |
| No rent recorded for 2+ months on a rental | underperforming |

Cap rate alone never triggers a downgrade — comparing cap rates across a handful of properties isn't statistically meaningful, so it's shown as context only. High equity (40%+) surfaces as an opportunity note, not a warning.

**Nothing here recommends selling.** It flags candidates with quantified reasons and leaves the decision to you.

## Valuations

Equity and LTV are only as current as the newest recorded value. Adding one moves `current_value` only when it's the newest on file, so backfilling an old appraisal can't clobber a current number. One valuation per property per day; re-valuing the same day overwrites.

## Tagging transactions

Attributing rent and repairs to a property is what turns the pro forma into observed performance. Tag from the transaction editor, or use `GET /api/properties/suggest-transactions`, which proposes matches from three sources:

1. The property's dedicated operating account
2. A `merchant_key` rule, compared through the same merchant normalizer that powers recurring-charge detection — so `ZELLE FROM TENANT J SMITH 0421` and `...0876` collapse onto one key
3. A `description_contains` substring

Suggestions never auto-apply. A mis-attributed rent payment would distort NOI, cash flow and the retirement projection with no visible cause.

## Under the hood

- `GET/POST/PUT/DELETE /api/properties[/{id}]`
- `GET /api/properties/portfolio`
- `GET/POST /api/properties/{id}/valuations`
- `GET /api/properties/suggest-transactions`

See also: [Loans](finances-loans.md), [Data model](../concepts/data-model.md).
