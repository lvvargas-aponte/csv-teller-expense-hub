# Upload CSV modal

> Source: `frontend/src/components/transactions/UploadCsvModal.js`, `backend/routers/transactions.py`, `backend/csv_parser.py`

Opens after picking a file from **📂 Upload CSV** on the Transactions tab.

## Purpose

Attach a CSV bank statement to a specific account so:

1. Transactions appear in the review queue.
2. The dashboard can group them by card.
3. A balance snapshot is recorded for net-worth history.

## Fields

| Field | Required | Notes |
|---|---|---|
| **Account** | Yes | Pick from your manual / synthetic accounts, or create a new one inline |
| **Statement balance** | Recommended | For credit cards, enter the amount **owed** as a positive number |
| **Statement date** | Recommended | Snapshot date used for net-worth history |

> Hint surfaced in the modal: *"Attaching transactions to an account lets dashboards group them by card and record a balance snapshot for net-worth history."*

## Supported formats

The parser at `backend/csv_parser.py` currently handles **Discover** and **Barclays** export formats. Other CSVs may parse if columns align (date, description, amount).

## Dedup

Within a single upload, identical (date + amount + description) entries are differentiated with a numeric suffix on the synthetic transaction ID. Across uploads, the same row uploaded twice produces a duplicate — review and delete if needed.

## Under the hood

- `POST /api/upload-csv` — multipart upload with the CSV file and account/balance metadata.

See also: [CSV ingest concept](../concepts/csv-ingest.md).
