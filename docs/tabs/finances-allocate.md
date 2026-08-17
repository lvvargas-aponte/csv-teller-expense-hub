# Finances → Spare Money

> Source: `frontend/src/components/finances/AllocatePage.js`, `frontend/src/components/finances/allocate/*`, `backend/allocation.py`

Where the next dollar should go, in order.

## Why it's a waterfall and not a recommendation

$500 spare rarely belongs in one place. It belongs partly in the employer match, partly in the buffer, partly against the card — and the split is what you actually want to know.

So each tier takes what it needs and passes the remainder down:

| | Tier | Takes |
|---|---|---|
| 1 | **Employer match** | up to the matched percentage of pay |
| 2 | **Emergency fund** | up to your target months of essentials |
| 3 | **Debt above your expected return** | the balance, highest rate or smallest first |
| 4 | **Tax-advantaged accounts** | this year's remaining room |
| 5 | **Property fund** | the monthly figure your goal needs |
| 6 | **Brokerage, or extra mortgage principal** | whatever's left |

**The ordering isn't taste.** A 50% employer match is a guaranteed 50% return, a 24% card is a guaranteed 24%, and a 3.25% mortgage is a guaranteed 3.25% — against a *hoped-for* 7% from the market. The only genuine judgement call is where the buffer sits, so that one is a setting.

## Guaranteed and projected are different claims

Paying a 24% card returns 24%, certainly. Investing returns 7% on average across decades that include years of losses. Rendering both as plain numbers would quietly say they're the same kind of promise, so they're labelled and coloured apart, and the projected line carries "not a promise; markets fall as well as rise".

## It asks rather than assumes

An unknown employer match produces a **question**, not an assumed zero. Same for contribution room. A missing input would otherwise silently start the waterfall a tier too low — and the tier it would skip is the highest-return one on the page.

Answer the question in the settings panel and the split changes.

## The skipped list is half the answer

"Why not just pay off the house?" is the question that actually gets asked, so it's answered on screen rather than omitted:

> **Extra principal on 123 Oak St** — At 3.25% it is cheaper than the 5.95% after-tax return you expect from investing, so paying it early costs you the difference. It also converts liquid money into equity you can only reach by borrowing or selling.

## Deferred interest, priced properly

A 0% promotional rate is not always a 0% cost of carry, and the difference between the two kinds is the whole point.

| | What happens | How it's ranked |
|---|---|---|
| **Deferred interest** | Interest accrues from day one at the regular rate, and is *waived* only if the balance clears by the deadline | At the **full regular rate**, today — it is already a full-rate debt |
| **A true promotional rate** | Nothing accrues until expiry | Blended: promo rate for the months left, regular rate for the rest of the year |

Ranking a deferred-interest balance at its nominal zero is how a card turns into a four-figure surprise. This is what the Debt Payoff page's `deferred_interest` flag was recorded for.

## Monthly or one-off

A recurring surplus and a bonus behave differently, so the cadence is an input. An employer match arrives through payroll — a lump sum can't capture one, and that tier says so instead of silently allocating to it.

## Taxes: explicit and shallow

Three things, and no more: contribution room, the stored withdrawal-tax assumption when comparing a mortgage against the market, and a caveat that mortgage interest may be deductible.

**This app does not compute a tax position.** Ask a CPA — and that sentence is in the payload, not just here.

## When it says its own answer is soft

The caveats are load-bearing. The buffer gates every tier below it, so a target built on an incomplete essentials figure waves money past a stop it should have hit:

> No recurring bills were detected, so $520/mo of essentials counts debt minimums only — rent, utilities and insurance are missing. The real emergency-fund target is very likely higher than $1,560.

It also prices the one contested ordering call rather than burying it: holding to a 3-month buffer while $8,000 sits at 27% costs about $2,160 a year, and it says so, with the setting to change it.

## Settings

Four facts the waterfall can't read from your transactions: whether your employer matches and on what terms, your gross pay, your buffer target in months, and what you've contributed to each account this year. Everything else — income, bills, debt rates, property equity — already comes from your data.

Contribution limits ship as editable defaults stamped with the year they were correct for, and the year is shown, because they change most years.

## Under the hood

- `POST /api/tools/allocate` — `{amount, cadence}`
- `GET/PUT /api/tools/allocation-settings`

See also: [Payoff Plan](finances-budgets.md), [Retirement](finances-retirement.md), [Equity & Deals](finances-equity.md).
