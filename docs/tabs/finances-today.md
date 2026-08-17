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

## Next actions

`/api/alerts` answers *what's wrong?*. This answers *what should I do about it?*, which is a different and more useful question — so every action carries an amount, a deadline where one exists, and what it protects.

### The rules

One deterministic function each, so a misfiring rule can be found and silenced without unpicking the ranking.

| Rule | Fires when |
|---|---|
| Daily allowance | You're past the month's plan, or ahead of pace |
| Budget overspend | A category is over its cap by $25+, quantified in dollars *and* days of allowance |
| Bill due soon | Within 7 days, flagged harder when the pool won't cover it |
| Goal behind | Pace is behind or stalled, with the monthly figure to recover |
| Emergency fund floor | Cash under 3 months of essentials — outranks every "invest more" suggestion |
| Promo APR expiring | Within 60 days with a balance still on the card |
| Extra payment impact | What $200/mo on the priciest loan actually buys |
| Credit utilization | A **card** over 50% of its limit, with the paydown that reaches 30% |
| Property underperforming | The classifier flagged it, with its quantified reasons |
| Surplus routing | Running under pace with expensive debt outstanding |
| Recurring anomaly | A subscription drifted 20%+ from its own median |

### Ranking

`(urgency, −dollar impact, kind)`. Urgency leads, so *"you're over budget today"* outranks *"you could save $38,000 over thirty years"* — the larger number is not the one you can still do something about this afternoon.

Capped at six. A coach that emits thirty items is a to-do list nobody reads.

### Dismissal

Dismissed actions are keyed by an id that embeds its period — `over_budget:Dining:2026-08` — so silencing August's warning correctly lets September's reappear.

### The LLM writes the voice, never the numbers

Amounts, impacts and reasons are all rule-derived, and are what the UI renders. An optional local-model pass rewrites the top few into a sentence of narration.

**Every figure in that narration is checked against the payload, and the whole paragraph is dropped if any number is unaccounted for.** A fabricated dollar amount the user then acts on is the worst thing this feature could produce, so it fails closed: no narration is strictly better than a wrong one. With Ollama unreachable the actions render exactly as they do with it.

### One rule set, two presentations

The dashboard's [Alerts card](finances-dashboard.md) is a flat projection of these same rules. It used to carry its own copies of the budget, goal, utilization and recurring-charge logic, and the two had already drifted — the two screens could disagree about whether a category was over budget. Dismiss an action here and it disappears from Alerts too.

## The rest of the page

- **Where this month goes** — a single bar splitting income into bills, debt, goals, spent, and left.
- **Coming up** — bills due, with a running "leaves $X after this clears".
- **Long-horizon anchors** — property equity, rental cash flow, and principal paid down. Daily restraint is easier to sustain when what it's buying is visible.

## Under the hood

- `GET /api/budgets/safe-to-spend` — optional `as_of=YYYY-MM-DD` recomputes for an earlier day
- `GET /api/coach/actions` — `?limit=`, `?as_of=`
- `POST /api/coach/narrate` — optional voice-over
- `POST/DELETE /api/coach/actions/{id}/dismiss`

See also: [Spare Money](finances-allocate.md), [Budgets](finances-budgets.md), [Goals](finances-goals.md), [Properties](finances-properties.md).
