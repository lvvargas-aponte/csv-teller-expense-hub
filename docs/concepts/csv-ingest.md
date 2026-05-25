# CSV ingest

> Source: `backend/csv_parser.py`, `backend/csv_watcher.py`, `backend/csv_watcher_script.py`, `backend/routers/transactions.py`

Two paths for getting transactions in via CSV: **direct upload** through the UI and an **auto-watch folder**.

## Direct upload

1. UI: **📂 Upload CSV** on the Transactions tab → opens [Upload CSV modal](../modals/upload-csv.md).
2. Backend: `POST /api/upload-csv` — multipart upload.
3. Parser detects format (Discover or Barclays) by header signature.
4. Each row becomes a `Transaction` with a synthetic ID derived from `(date, amount, description)` plus a per-run dedup counter.
5. Account is attached so dashboards group by card; an optional `BalanceSnapshot` is recorded with the statement balance and date.

## Auto-watch

Run `./run_csv_watcher.sh` (or `python backend/csv_watcher_script.py`) and drop CSVs into `csv_imports/`.

- Successfully parsed → moves to `csv_imports/processed/`
- Parse failure → moves to `csv_imports/failed/` with an error log

## Dedup model

The parser generates a dedup ID by hashing `(date, amount, description)`. Within one run, identical rows get a numeric suffix so they don't collide. Across uploads, the same row uploaded twice will create a duplicate — by design (fully-automatic dedup is risky for consumer-grade CSVs). Review the queue and delete or unmark obvious duplicates.

## Adding new bank formats

The parser is dispatch-by-header. Add a new branch in `csv_parser.py` keyed off the first-row signature, return rows shaped like the existing branches.
