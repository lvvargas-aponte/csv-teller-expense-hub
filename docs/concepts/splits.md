# Splits & shared expenses

> Source: `backend/db/models.py` (`Transaction`), `frontend/src/components/transactions/SplitPill.js`, `SplitAdjustRow.js`

Every transaction is either **personal** or **shared** between the two configured household members.

## Schema fields

On the `Transaction` model:

| Field | Type | Notes |
|---|---|---|
| `is_shared` | bool | The master flag |
| `who` | string | Who paid — typically `PERSON_1_NAME` or `PERSON_2_NAME` |
| `what` | string | Free-text label (e.g., "Groceries", "Rent") |
| `person_1_owes` | float | Owed by person 1 |
| `person_2_owes` | float | Owed by person 2 |
| `notes` | string | Free text — exported with the row |

For an even split, `person_1_owes == person_2_owes == abs(amount) / 2`.

## UI affordances

- **`P` / `½` pill** on each row — quick toggle. `½` means shared with an even split.
- **🧮 inline adjust** — for custom amounts (e.g., one person owes more this month).
- **Bulk actions** — select rows then **Mark personal** or **50/50**.
- **EditModal** — full control of all fields at once.

## Export

When **📊 Send to Sheet** runs, only `is_shared = True` transactions are written. Nothing is removed locally — the rows stay in the database and remain visible under [Transactions → History](../tabs/transactions-history.md). Because the export does not clear anything, running it twice for the same month appends those rows to the sheet twice.

## Why two columns instead of one ratio?

The split model is **absolute**, not proportional, so totals always reconcile. If a row is `$200` and person 1 owes `$120`, person 2 owes `$80` — the sum equals the absolute amount of the transaction.
