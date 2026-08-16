# Finances → Equity & Deals

> Source: `frontend/src/components/finances/EquityPage.js`, `frontend/src/components/finances/equity/*`, `properties.compute_usable_equity()`, `properties.analyze_deal()`

What you could borrow against what you own — and what borrowing it would cost.

## The rule this page follows

**No extractable figure appears without its cost beside it.**

An amount you could pull out looks like free money. It is a payment increase. So every scenario carries the new payment, the payment delta, the DSCR that survives it, and the resulting cash flow — rendered directly beneath the amount, never behind a toggle.

Where borrowing would flip a property from paying you to costing you, the card says so in those words.

## Two scenarios per property

| | Cash-out refinance | HELOC |
|---|---|---|
| Ceiling | 75% LTV (adjustable) | 85% CLTV (adjustable) |
| Replaces | the whole existing balance | nothing — sits behind it |
| Cost shown | new P&I payment, delta, DSCR after | interest-only on a full draw |
| Rate | fixed at the assumed rate | **variable** |

Closing costs are shown as a line item rather than silently netted off, so the gross and net figures are both visible and the 2% assumption can be argued with.

The HELOC payment is interest-only on a full draw at today's rate, and labelled variable. A fixed-looking payment on a floating rate is a trap.

## When there's no valuation

A property without a current value returns `available: false` with an explanation, rather than reporting zero — zero reads as "no equity", which is a different and wrong claim. The portfolio view names those properties instead of quietly lowering the total.

## Deal analyzer

Model a purchase before you make it: price, down payment, rate, term, expected rent, vacancy, operating expenses, closing costs, rehab.

**The headline is portfolio cash flow, not the deal's.** When the down payment comes from a HELOC or cash-out refinance on something you already own, that borrowing has a carrying cost. A deal can be positive standalone and still reduce your total monthly income — that's the specific failure this framing exists to catch, and it's the honest frame for a leverage question.

Alongside: cap rate, cash-on-cash, DSCR, total cash needed, and the break-even rent at which the property exactly covers itself.

### Sensitivity

Three deterministic rows — rent 10% below plan, vacancy 5 points worse, rate 1 point higher. Cheapest possible risk disclosure, and enough to show whether a deal survives being slightly wrong.

### Warnings come first

Warnings render **above** the attractive numbers, not below them:

- the property loses money on its own
- the deal is positive standalone but the borrowing behind it costs more than it earns
- DSCR under the 1.25 lenders look for
- cash flow turns negative under any sensitivity scenario

This is the screen that makes over-leverage feel easy. The guardrails lead.

## Under the hood

- `GET /api/equity/capacity` — portfolio-wide, `?max_ltv_pct=` / `?max_cltv_pct=`
- `GET /api/equity/capacity/{property_id}` — one property
- `POST /api/equity/analyze-deal`

See also: [Properties](finances-properties.md), [Loans](finances-loans.md), [Retirement](finances-retirement.md).
