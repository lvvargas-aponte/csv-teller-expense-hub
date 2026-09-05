# Splits & shared expenses

> Source: `backend/db/models.py` (`Transaction`), `frontend/src/components/transactions/SplitPill.js`, `SplitAdjustRow.js`, `backend/routers/sync.py`, `frontend/src/components/shared/*`

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
- **Transaction detail** — expanding a row gives full control of every field at once.

## Export

When **📊 Send to Sheet** runs, only `is_shared = True` transactions are written. Nothing is removed locally — the rows stay in the database and remain visible under [Transactions → History](../tabs/transactions-history.md). Because the export does not clear anything, running it twice for the same month appends those rows to the sheet twice.

## Why two columns instead of one ratio?

The split model is **absolute**, not proportional, so totals always reconcile. If a row is `$200` and person 1 owes `$120`, person 2 owes `$80` — the sum equals the absolute amount of the transaction.

## Two-way sync

The one-way export above is the legacy path. The current flow is
[Transactions → Shared](../tabs/transactions-shared.md): each install pushes its own shared rows to
the sheet and pulls the other's, so both sides see the same month and can settle it.

| Concept | Where it lives |
|---|---|
| Who this install is, and its person slot | `instance_identity` (`0015`) |
| The other member's install | `peers` (`0016`, `0017`) |
| Rows pulled from the peer | `peer_shared_transactions` (`0016`) |
| Push/pull history and per-row watermarks | `sync_runs`, `sync_row_state` (`0018`) |
| Edits the peer made to rows you had synced | `sync_corrections` (`0018`) |
| Per-month **ready** / **paid** state | `period_settlements` (`0019`) |

**Only rows with a split count toward settle-up.** A row marked shared with both `*_owes` blank is
surfaced in the attention strip rather than silently counted as zero.

Settlement is last-writer-safe: if both sides mark a month paid at once, the loser's call returns
`409` and its page reloads onto the record that won.
