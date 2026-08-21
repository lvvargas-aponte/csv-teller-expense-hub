# Finances → Retirement

> Source: `frontend/src/components/finances/RetirementPage.js`, `frontend/src/components/finances/retirement/*`, `backend/retirement.py`

When the rentals and the portfolio can carry you.

## The mechanic this page exists to show

Rent drifts up with inflation. A fixed mortgage payment does not. And then the mortgage **ends**.

The year a loan is retired, that property's net cash flow jumps by the entire payment — permanently. Stack three or four of those and the rental income line crosses the spending line years before a pure withdrawal strategy would get you there. That crossing is the plan, so the projection is built to show it rather than to produce a single number in isolation.

The **When the mortgages finish** section lists each payoff year. Those are the steps in the chart.

## What "earliest retirement year" means

The first year income covers spending **and keeps covering it** for every year after.

Not the first crossing. Inflation can outrun a fixed income stream, so a year that works and then stops working is not a retirement date — reporting one would be a lie with a number attached. The projection scans backwards from the horizon to find the start of the final unbroken run.

## Your retirement goal

One number to aim at, and how close the portfolio is to it.

The target is **not a second model**. It is the same feasibility test, rearranged to solve for the balance:

```
rental_net + balance × swr × (1 − tax) + social_security  ≥  spending
balance  ≥  (spending − rental_net − social_security) / (swr × (1 − tax))
```

So the goal can never disagree with the retirement year shown above it. Fund it exactly and year zero turns feasible — that invariant is asserted in the tests, and it's why the target rounds *up* to the cent. A target rounded down is one you can hit and still fall short.

Everything is in **today's dollars**, read off year zero, so it's directly comparable to the balance you hold now. Two consequences, both deliberate:

- **Rental profit is netted against today's debt service**, which makes the target conservative. The card also shows the gross figure — what the same spending would need with no rentals at all — so the properties' contribution is visible.
- **Social Security is subtracted only once you're eligible.** A target that quietly assumes an income stream you can't draw for twenty years is not a target. Before the start age the card says so rather than silently inflating the number.

At a 4% withdrawal rate with 15% tax on withdrawals, the effective rate is 3.4% — so spending of $60,000/yr with no other income is a target of about $1.76m, or 29.4×. The familiar "25× your spending" rule is the same arithmetic with the tax drag left out.

### Two targets, because one would mislead

Netting rent against *today's* debt service understates the properties badly, and understating them is the one error this page must not make. While a mortgage runs, most of the rent is the bank's — so the headline target reads as though the rentals barely contribute, when the entire plan is that they eventually carry most of the load.

So the card reports **`after_payoff`** alongside it: the same target with the debt service gone and the rent kept, dated to the last loan's payoff. It is the number the buy-and-hold strategy is actually aiming at.

On real data the gap is not subtle — $1.63m while the mortgages run against $770k once they're done, because rental profit goes from $4,630/yr to $33,826/yr without rents changing at all. Showing only the first would misrepresent the strategy; showing only the second would flatter it. Both are reported: one is where you stand, the other is where the plan lands.

It's omitted entirely when there are no loans left to retire, since the same number under a hopeful label would imply a gain that isn't coming.

There is no goal when there's no spending figure to build one from, and none if the withdrawal rate is zero — the same standard the rest of the page holds to.

## What's projected each year

| | |
|---|---|
| **Investments** | Compound at the assumed return; contributions stop at retirement |
| **Property value** | Appreciates at the assumed rate, per-property override available |
| **Loan balances** | Step down through the real amortization schedule |
| **Rental income** | NOI grows with rents; debt service drops to zero at payoff |
| **Withdrawals** | Safe withdrawal rate on investments, after tax |
| **Social Security** | From its start age, inflated |
| **Spending need** | Your target, inflated forward |

## When it declines to answer

**No spending target.** The default is derived from your trailing spending — better than a guessed percentage of income, because it's what your household actually costs. But that needs at least **three complete months** of transaction history. Annualizing one month multiplies whatever that month happened to contain, including a bulk CSV import, by twelve.

Against real data with a single month on file, the naive version produced a $499,103/yr target and a meaningless "you need $9,607/mo". It now declines and explains, rather than inventing a number. Set a monthly figure in the assumptions to proceed.

**Not reachable.** When no year works, the projection solves by bisection for the monthly contribution that would close the gap — and returns nothing rather than a search ceiling when no contribution does. A spending target that can't be funded should say so.

## Deterministic, and labelled

`monte_carlo` is always false. Three sensitivity rows — returns 5% instead of 7%, spending $1,000/mo higher, rents growing 1% instead of 3% — stand in for a probability figure that assumptions this soft could not honestly support. Each shows how many years the answer slips.

## Assumptions

Every field is optional and falls back to a default rather than freezing today's default into your record, so improving a default later benefits you if you never set it. **Try it without saving** runs a scenario without persisting it.

## Under the hood

- `GET/PUT /api/retirement/assumptions`
- `GET /api/retirement/projection` — `?as_of=`, `?include_sensitivity=`
- `POST /api/retirement/projection` — what-if against supplied assumptions

See also: [Properties](finances-properties.md), [Equity & Deals](finances-equity.md).
