# Finances → Bills

> Source: `backend/routers/bills.py`, `frontend/src/components/finances/cards/*`

Upcoming bills and detected recurring charges (subscriptions). The dashboard **RecurringChargesCard** reads the same data.

## What you see

- Upcoming credit-card statement & due dates per card
- Subscriptions detected from transaction history (description + cadence + last amount)
- Manual bill entries (if any)

## How recurrence is detected

The backend looks at transaction history grouped by normalized description, finds entries that recur on a roughly monthly cadence, and surfaces them as recurring charges. (See `backend/routers/bills.py` for the heuristic.)

## Under the hood

- `GET /api/bills/upcoming`
