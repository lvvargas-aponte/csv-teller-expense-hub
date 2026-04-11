"""Tests for main.py API endpoints."""
import io
from unittest.mock import patch


# conftest.py supplies: client, clear_storage (autouse), sample_discover_csv, sample_barclays_csv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _upload_csv(client, content: str, filename: str = "test.csv"):
    """POST a CSV string to /api/upload-csv and return the response."""
    return client.post(
        "/api/upload-csv",
        files={"file": (filename, io.BytesIO(content.encode("utf-8")), "text/csv")},
    )


def _upload_and_get_id(client, csv_content: str, filename: str = "test.csv") -> str:
    """Upload CSV and return the ID of the first transaction."""
    res = _upload_csv(client, csv_content, filename)
    assert res.status_code == 200
    txns = client.get("/api/transactions/all").json()
    return txns[0]["id"]


# ---------------------------------------------------------------------------
# Basic routes
# ---------------------------------------------------------------------------

class TestHealthAndRoot:
    def test_root_returns_200(self, client):
        res = client.get("/")
        assert res.status_code == 200

    def test_health_returns_healthy(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "healthy"


# ---------------------------------------------------------------------------
# Upload CSV
# ---------------------------------------------------------------------------

class TestUploadCSV:
    def test_upload_discover_csv(self, client, sample_discover_csv):
        res = _upload_csv(client, sample_discover_csv, "Discover-Statement.csv")
        assert res.status_code == 200
        assert res.json()["count"] == 2

    def test_upload_barclays_csv(self, client, sample_barclays_csv):
        res = _upload_csv(client, sample_barclays_csv, "creditcard.csv")
        assert res.status_code == 200
        assert res.json()["count"] == 2

    def test_upload_latin1_encoded_csv(self, client):
        """CSV with a Latin-1 encoded character (e.g. £) must not raise a 500."""
        latin1_csv = "Trans. Date,Post Date,Description,Amount,Category\n01/15/2024,01/16/2024,CAF\xe9,-5.00,Dining\n"
        res = client.post(
            "/api/upload-csv",
            files={"file": ("test.csv", io.BytesIO(latin1_csv.encode("latin-1")), "text/csv")},
        )
        assert res.status_code == 200
        assert res.json()["count"] == 1

    def test_upload_empty_csv_returns_zero_count(self, client):
        res = _upload_csv(client, "", "empty.csv")
        assert res.status_code == 200
        assert res.json()["count"] == 0

    def test_upload_stores_transactions(self, client, sample_discover_csv):
        _upload_csv(client, sample_discover_csv, "Discover-Statement.csv")
        all_txns = client.get("/api/transactions/all").json()
        assert len(all_txns) == 2

    def test_upload_with_utf8_bom(self, client):
        """CSV with UTF-8 BOM (common in Excel exports) must be parsed correctly."""
        bom_csv = "\ufeffTrans. Date,Post Date,Description,Amount,Category\n01/15/2024,01/16/2024,AMAZON,-19.99,Shopping\n"
        res = client.post(
            "/api/upload-csv",
            files={"file": ("bom.csv", io.BytesIO(bom_csv.encode("utf-8-sig")), "text/csv")},
        )
        assert res.status_code == 200
        assert res.json()["count"] == 1


# ---------------------------------------------------------------------------
# Get all transactions
# ---------------------------------------------------------------------------

class TestGetAllTransactions:
    def test_empty_returns_empty_list(self, client):
        res = client.get("/api/transactions/all")
        assert res.status_code == 200
        assert res.json() == []

    def test_returns_uploaded_transactions(self, client, sample_discover_csv):
        _upload_csv(client, sample_discover_csv, "Discover-Statement.csv")
        res = client.get("/api/transactions/all")
        assert res.status_code == 200
        assert len(res.json()) == 2


# ---------------------------------------------------------------------------
# Update single transaction
# ---------------------------------------------------------------------------

class TestUpdateTransaction:
    def test_mark_shared(self, client, sample_discover_csv):
        txn_id = _upload_and_get_id(client, sample_discover_csv, "Discover-Statement.csv")
        res = client.put(f"/api/transactions/{txn_id}", json={
            "is_shared": True, "who": "Alice", "what": "Coffee",
            "person_1_owes": 2.25, "person_2_owes": 2.25, "notes": "test",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["is_shared"] is True
        assert data["who"] == "Alice"

    def test_person_owes_fields_saved(self, client, sample_discover_csv):
        txn_id = _upload_and_get_id(client, sample_discover_csv, "Discover-Statement.csv")
        client.put(f"/api/transactions/{txn_id}", json={
            "is_shared": True, "person_1_owes": 10.00, "person_2_owes": 5.00,
        })
        all_txns = client.get("/api/transactions/all").json()
        txn = next(t for t in all_txns if t["id"] == txn_id)
        assert txn["person_1_owes"] == 10.00
        assert txn["person_2_owes"] == 5.00

    def test_update_nonexistent_returns_404(self, client):
        res = client.put("/api/transactions/no-such-id", json={"is_shared": False})
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# Bulk update
# ---------------------------------------------------------------------------

class TestBulkUpdate:
    def test_bulk_mark_shared(self, client, sample_discover_csv):
        _upload_csv(client, sample_discover_csv, "Discover-Statement.csv")
        txns = client.get("/api/transactions/all").json()
        ids = [t["id"] for t in txns]

        res = client.put("/api/transactions/bulk", json={
            "transaction_ids": ids, "is_shared": True, "split_evenly": True,
        })
        assert res.status_code == 200
        assert res.json()["updated"] == 2
        assert all(t["is_shared"] for t in res.json()["transactions"])

    def test_bulk_mark_personal(self, client, sample_discover_csv):
        _upload_csv(client, sample_discover_csv, "Discover-Statement.csv")
        txns = client.get("/api/transactions/all").json()
        ids = [t["id"] for t in txns]

        # First mark shared, then revert to personal
        client.put("/api/transactions/bulk", json={"transaction_ids": ids, "is_shared": True})
        res = client.put("/api/transactions/bulk", json={"transaction_ids": ids, "is_shared": False})
        assert res.status_code == 200
        assert all(not t["is_shared"] for t in res.json()["transactions"])

    def test_split_evenly_calculates_half(self, client, sample_discover_csv):
        _upload_csv(client, sample_discover_csv, "Discover-Statement.csv")
        txns = client.get("/api/transactions/all").json()
        starbucks = next(t for t in txns if t["description"] == "STARBUCKS")

        res = client.put("/api/transactions/bulk", json={
            "transaction_ids": [starbucks["id"]], "is_shared": True, "split_evenly": True,
        })
        updated = res.json()["transactions"][0]
        expected_half = round(abs(starbucks["amount"]) / 2, 2)
        assert updated["person_1_owes"] == expected_half
        assert updated["person_2_owes"] == expected_half

    def test_not_found_ids_are_reported(self, client):
        res = client.put("/api/transactions/bulk", json={
            "transaction_ids": ["ghost-1", "ghost-2"], "is_shared": True,
        })
        assert res.status_code == 200
        assert res.json()["not_found"] == ["ghost-1", "ghost-2"]
        assert res.json()["updated"] == 0


# ---------------------------------------------------------------------------
# Send to Google Sheet
# ---------------------------------------------------------------------------

class TestSendToGSheet:
    def test_no_shared_transactions_returns_zero(self, client, sample_discover_csv):
        _upload_csv(client, sample_discover_csv, "Discover-Statement.csv")
        res = client.post("/api/send-to-gsheet")
        assert res.status_code == 200
        assert res.json()["count"] == 0

    def test_success_removes_shared_from_storage(self, client, sample_discover_csv):
        """Shared transactions must be removed from in-memory storage after a successful send."""
        _upload_csv(client, sample_discover_csv, "Discover-Statement.csv")
        txns = client.get("/api/transactions/all").json()
        txn_id = txns[0]["id"]

        # Mark one transaction as shared
        client.put(f"/api/transactions/{txn_id}", json={"is_shared": True})

        with patch("main.append_to_sheet", return_value=1) as mock_append:
            res = client.post("/api/send-to-gsheet")

        assert res.status_code == 200
        assert res.json()["count"] == 1
        mock_append.assert_called_once()

        remaining = client.get("/api/transactions/all").json()
        remaining_ids = {t["id"] for t in remaining}
        assert txn_id not in remaining_ids, "Sent transaction should be removed from queue"

    def test_gsheet_failure_does_not_delete_transactions(self, client, sample_discover_csv):
        """If append_to_sheet raises, the transaction must NOT be removed from storage."""
        _upload_csv(client, sample_discover_csv, "Discover-Statement.csv")
        txns = client.get("/api/transactions/all").json()
        txn_id = txns[0]["id"]

        client.put(f"/api/transactions/{txn_id}", json={"is_shared": True})

        with patch("main.append_to_sheet", side_effect=Exception("GSheet unavailable")):
            res = client.post("/api/send-to-gsheet")

        assert res.status_code == 500

        remaining = client.get("/api/transactions/all").json()
        remaining_ids = {t["id"] for t in remaining}
        assert txn_id in remaining_ids, "Transaction must remain in queue when GSheet call fails"

    def test_no_spreadsheet_id_returns_500(self, client, monkeypatch):
        monkeypatch.setattr("main.SPREADSHEET_ID", None)
        res = client.post("/api/send-to-gsheet")
        assert res.status_code == 500


# ---------------------------------------------------------------------------
# Person names
# ---------------------------------------------------------------------------

class TestPersonNames:
    def test_returns_configured_names(self, client, monkeypatch):
        monkeypatch.setattr("main.PERSON_1_NAME", "Alice")
        monkeypatch.setattr("main.PERSON_2_NAME", "Bob")
        res = client.get("/api/config/person-names")
        assert res.status_code == 200
        data = res.json()
        assert data["person_1"] == "Alice"
        assert data["person_2"] == "Bob"
