# Finances → Net Worth

> Source: `frontend/src/components/finances/NetWorthPage.js`, `backend/routers/balances.py`

Everything you own, minus everything you owe — stated once, in one place.

## The number

The headline is `summary.net_worth`, computed server-side in
`routers/balances._build_summary`. The page never re-derives it; the rows below
are the terms of that same sum, so the breakdown reconciles exactly.

```
net worth = cash + investments + property value
            − credit debt − unlinked property debt
```

## Why property equity counts

A mortgage arrives from the bank as a `credit` account and is subtracted like
any other liability. If the house securing it contributed nothing, a household
with real equity would read as deeply negative — which is what the old
Accounts-page rail card did, since it computed cash minus debt and called that
net worth. Property value is added here, so equity you hold in an asset is part
of the total.

## Why the mortgage isn't subtracted twice

Property debt splits in two, and the summary reports both halves:

| Field | Meaning | Already in `total_credit_debt`? |
|---|---|---|
| `total_property_debt_linked` | Loan tied to a synced account | **Yes** — do not subtract again |
| `total_property_debt_unlinked` | Hand-entered loan backed by no account | No — subtracted here |

So the Liabilities group lists credit debt (annotated with how much of it is
mortgage balances) plus only the unlinked remainder. Adding
`total_property_debt` on top would double-count the mortgage.

See `properties.compute_real_estate_position` for where the split is made.

## Reconciliation check

If the itemised rows don't total the reported net worth, the page says so
outright rather than quietly showing rows that don't add up — a warning that
something entered the total without an itemised row to explain it.

## Unvalued properties

A property with no valuation on file contributes nothing to net worth and is
named explicitly, so the gap is something you can go fill on
[Properties](finances-properties.md) rather than a silent omission.

## Trend

An area chart of net worth over time, built from balance snapshots — so it
begins when your snapshot history does, not when you bought the assets.

Backend: `GET /api/balances/summary`, `GET /api/dashboard`.
