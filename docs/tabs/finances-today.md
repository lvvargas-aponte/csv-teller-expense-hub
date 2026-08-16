# Finances → Today

> Source: `frontend/src/components/finances/TodayPage.js`, `frontend/src/components/finances/cards/SafeToSpendCard.js`, `analytics.compute_safe_to_spend()`

One number: what you can spend today without derailing anything you've committed to.

## How the number is built

```
income                        detected paychecks + inbound transfers
                              + positive rental cash flow
− fixed bills                 recurring charges in bill categories
− minimum debt payments       card minimums + loan payments (incl. escrow)
− required goal contributions what your goals need monthly to land on time
─────────────────────────────
= discretionary pool
− spent so far this month     discretionary only; bills already counted above
─────────────────────────────
= remaining ÷ days left       (today counts as a day)
```

## Overspending lowers tomorrow

This is the mechanism, not a feature bolted on top. `remaining` is recomputed from your actual month-to-date spend every time the page loads, and the day count shrinks by one each day. Spend $400 over today and tomorrow's number drops by roughly $400 ÷ days remaining.

There is deliberately **no carry-over ledger**. A stored running balance would be a second source of truth, free to drift from the transactions it claims to summarize. Everything here is derived on read.

The card shows yesterday's figure alongside today's, so a drop reads as a consequence of what you spent rather than unexplained movement.

## When it refuses to answer

**No income detected** → the card explains itself instead of showing a number. A safe-to-spend figure derived from a guessed salary is worse than no figure at all. `compute_income_estimate()` needs a recurring pattern; variable or self-employment income may not produce one.

**Negative pool** → the daily number clamps to zero and the card reports the shortfall. "You're $340 past the month's plan" is something you can act on; a negative allowance is not.

## Why bills aren't double-counted

A utility bill is subtracted once, as a commitment. Month-to-date spend then skips transactions in always-recurring categories and any merchant already counted as a bill — otherwise the same $180 would come out of the pool twice.

The categories excluded this way are listed on the page. The most common failure of a number like this is the reader not believing it, so the workings are shown rather than hidden.

## Escrow, in two places

Loan escrow **counts** toward debt minimums here: that money genuinely leaves the account every month.

Escrow is **excluded** from debt service in [property economics](finances-properties.md), because there it would double-count against taxes and insurance already in the operating-expense model.

Both are correct in their own context. The distinction is commented at both sites in the code.

## The rest of the page

- **Where this month goes** — a single bar splitting income into bills, debt, goals, spent, and left.
- **Coming up** — bills due, with a running "leaves $X after this clears".
- **Long-horizon anchors** — property equity, rental cash flow, and principal paid down. Daily restraint is easier to sustain when what it's buying is visible.

## Under the hood

- `GET /api/budgets/safe-to-spend` — optional `as_of=YYYY-MM-DD` recomputes for an earlier day

See also: [Budgets](finances-budgets.md), [Goals](finances-goals.md), [Properties](finances-properties.md).
