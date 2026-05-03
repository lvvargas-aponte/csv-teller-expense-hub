"""Unit-style port of ``tests/test_csv_upload_metadata.py``.

Same assertions, sourced from ``accounts_repo_memory`` instead of SQL.
"""
import io

import state
from db import accounts_repo_memory


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
    return sum(1 for s in accounts_repo_memory.get_snapshots() if s["account_id"] == account_id)


class TestUploadWithoutMetadata:
    def test_existing_behavior_preserved(self, client):
        """No metadata → no account, no snapshot, txns unchanged."""
        res = _post(client)
        assert res.status_code == 200
        body = res.json()
        assert body["count"] == 2
        assert body["account_id"] is None

        # No csv-synth account exists
        csv_accts = [a for a in accounts_repo_memory.get_accounts().values() if a["source"] == "csv"]
        assert csv_accts == []

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

        record = accounts_repo_memory.get_accounts()[acct_id]
        assert record["source"] == "csv"
        assert record["manual"] is True
        assert record["institution"] == "Discover"
        assert record["type"] == "credit"

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
        snaps = [s for s in accounts_repo_memory.get_snapshots() if s["account_id"] == acct_id]
        assert len(snaps) == 1
        snap = snaps[0]
        assert snap["source"] == "csv"
        assert float(snap["ledger"]) == 1250.75
        assert float(snap["available"]) == 0.0
        assert snap["captured_at"].startswith("2026-03-31")

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
        snap = next(s for s in accounts_repo_memory.get_snapshots() if s["account_id"] == acct_id)
        assert float(snap["available"]) == 5000.00
        assert float(snap["ledger"]) == 0.0

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
        assert _count_snapshots(acct_id) == 1
        snap = next(s for s in accounts_repo_memory.get_snapshots() if s["account_id"] == acct_id)
        # 4.50 + 29.99 = 34.49
        assert float(snap["ledger"]) == 34.49

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

        for txn in state.stored_transactions.values():
            assert txn.get("account_id") == acct_id

        # POST created 1 snapshot, upload added another
        assert _count_snapshots(acct_id) == pre_snapshots + 1

    def test_unknown_account_id_is_404(self, client):
        res = _post(
            client,
            extra_form={"account_id": "nonexistent"},
        )
        assert res.status_code == 404
