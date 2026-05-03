"""CSV upload with optional statement metadata.

Extends the Phase 5 balance-snapshots coverage: when the user uploads a
CSV *with* statement-balance metadata, we should upsert a csv-synth
account, attach ``account_id`` to every parsed transaction, and append a
``balance_snapshots`` row dated to the statement. Without metadata, the
endpoint must behave exactly as it did pre-migration (no account, no
snapshot, NULL account_id on txns).
"""
import io

from sqlalchemy import text

import state
from db.base import sync_engine


_DISCOVER_CSV = (
    "Trans. Date,Post Date,Description,Amount,Category\n"
    "03/15/2026,03/16/2026,STARBUCKS,-4.50,Restaurants\n"
    "03/16/2026,03/17/2026,AMAZON PRIME,-29.99,Shopping\n"
)


def _post(client, *, extra_form=None, filename="march.csv"):
    data = {}
    if extra_form:
        data.update(extra_form)
    return client.post(
        "/api/upload-csv",
        files={"file": (filename, io.BytesIO(_DISCOVER_CSV.encode("utf-8")), "text/csv")},
        data=data,
    )


def _count_snapshots(account_id: str) -> int:
    with sync_engine.connect() as conn:
        return int(
            conn.execute(
                text("SELECT COUNT(*) FROM balance_snapshots WHERE account_id = :id"),
                {"id": account_id},
            ).scalar()
            or 0
        )


class TestUploadWithoutMetadata:
    def test_existing_behavior_preserved(self, client):
        """No metadata → no account, no snapshot, txns unchanged."""
        res = _post(client)
        assert res.status_code == 200
        body = res.json()
        assert body["count"] == 2
        assert body["account_id"] is None

        # No csv-synth account exists
        with sync_engine.connect() as conn:
            count = int(
                conn.execute(
                    text("SELECT COUNT(*) FROM accounts WHERE source = 'csv'")
                ).scalar() or 0
            )
        assert count == 0

        # Stored transactions have NULL account_id
        for txn in state.stored_transactions.values():
            assert txn.get("account_id") in (None, "")


class TestUploadCreatingNewAccount:
    def test_creates_csv_account_and_threads_account_id(self, client):
        res = _post(
            client,
            extra_form={
                "institution":       "Discover",
                "name":              "Discover It Card",
                "type":              "credit",
                "statement_balance": "1250.75",
                "statement_date":    "2026-03-31T00:00:00+00:00",
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        acct_id = body["account_id"]
        assert acct_id and acct_id.startswith("csv_")
        assert body["count"] == 2

        # Structured accounts row exists with source='csv' and manual=true
        with sync_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT source, manual, institution, name, type "
                    "FROM accounts WHERE id = :id"
                ),
                {"id": acct_id},
            ).fetchone()
        assert row is not None
        assert row[0] == "csv"
        assert row[1] is True
        assert row[2] == "Discover"
        assert row[4] == "credit"

        # Every stored transaction got the account_id threaded through
        for txn in state.stored_transactions.values():
            assert txn.get("account_id") == acct_id

    def test_statement_balance_creates_snapshot_with_statement_date(self, client):
        res = _post(
            client,
            extra_form={
                "institution":       "Discover",
                "name":              "Discover It Card",
                "type":              "credit",
                "statement_balance": "1250.75",
                "statement_date":    "2026-03-31T00:00:00+00:00",
            },
        )
        acct_id = res.json()["account_id"]
        assert _count_snapshots(acct_id) == 1

        with sync_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT source, available, ledger, captured_at "
                    "FROM balance_snapshots WHERE account_id = :id"
                ),
                {"id": acct_id},
            ).fetchone()
        assert row[0] == "csv"
        # credit type puts the statement balance in `ledger`, leaves available at 0
        assert float(row[2]) == 1250.75
        assert float(row[1]) == 0.0
        # captured_at is the statement date, not NOW()
        assert row[3].isoformat().startswith("2026-03-31")

    def test_depository_routes_balance_into_available(self, client):
        res = _post(
            client,
            extra_form={
                "institution":       "Chase",
                "name":              "Checking",
                "type":              "depository",
                "statement_balance": "5000.00",
                "statement_date":    "2026-03-31T00:00:00+00:00",
            },
        )
        acct_id = res.json()["account_id"]
        with sync_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT available, ledger FROM balance_snapshots "
                    "WHERE account_id = :id"
                ),
                {"id": acct_id},
            ).fetchone()
        assert float(row[0]) == 5000.00
        assert float(row[1]) == 0.0

    def test_missing_statement_balance_falls_back_to_transaction_sum(self, client):
        """Without a supplied balance, the upload derives one by summing the
        parsed transactions (debits − credits for credit accounts) and writes
        a single snapshot at the derived balance."""
        res = _post(
            client,
            extra_form={
                "institution": "Discover",
                "name":        "Discover It Card",
                "type":        "credit",
            },
        )
        acct_id = res.json()["account_id"]
        assert acct_id is not None
        # Discover sample fixture has two debits totalling 4.50 + 29.99 = 34.49
        assert _count_snapshots(acct_id) == 1
        with sync_engine.connect() as conn:
            ledger = conn.execute(
                text("SELECT ledger FROM balance_snapshots WHERE account_id = :id"),
                {"id": acct_id},
            ).scalar()
        assert float(ledger) == 34.49

    def test_invalid_type_is_422(self, client):
        res = _post(
            client,
            extra_form={
                "institution": "X",
                "name":        "Y",
                "type":        "checking",  # wrong — must be depository/credit
            },
        )
        assert res.status_code == 422


class TestUploadAttachingToExistingAccount:
    def test_attach_to_existing_manual_account(self, client):
        created = client.post(
            "/api/balances/manual",
            json={
                "institution": "Discover",
                "name":        "Discover It Card",
                "type":        "credit",
                "subtype":     "",
                "available":   0.0,
                "ledger":      0.0,
            },
        )
        acct_id = created.json()["id"]
        pre_snapshots = _count_snapshots(acct_id)

        res = _post(
            client,
            extra_form={
                "account_id":        acct_id,
                "statement_balance": "800.00",
                "statement_date":    "2026-03-31T00:00:00+00:00",
            },
        )
        assert res.status_code == 200, res.text
        assert res.json()["account_id"] == acct_id

        # Txns threaded through
        for txn in state.stored_transactions.values():
            assert txn.get("account_id") == acct_id

        # One more snapshot than we started with (POST created 1, upload adds 1)
        assert _count_snapshots(acct_id) == pre_snapshots + 1

    def test_unknown_account_id_is_404(self, client):
        res = _post(
            client,
            extra_form={"account_id": "nonexistent"},
        )
        assert res.status_code == 404
