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
