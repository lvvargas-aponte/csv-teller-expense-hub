"""Tests for dedupe key, dedupe endpoint, and per-id DELETE."""
import state
from csv_parser import dedupe_key


class TestDedupeKey:
    def test_normalizes_description_punctuation_and_case(self):
        a = dedupe_key("2026-01-15", 4.50, "STARBUCKS #1234", "debit")
        b = dedupe_key("2026-01-15", 4.50, "starbucks 1234", "DEBIT")
        assert a == b

    def test_amount_rounded_to_2dp(self):
        a = dedupe_key("2026-01-15", 4.5, "x", "debit")
        b = dedupe_key("2026-01-15", 4.500001, "x", "debit")
        assert a == b

    def test_different_dates_do_not_match(self):
        a = dedupe_key("2026-01-15", 4.50, "x", "debit")
        b = dedupe_key("2026-01-16", 4.50, "x", "debit")
        assert a != b

    def test_different_direction_does_not_match(self):
        a = dedupe_key("2026-01-15", 4.50, "x", "debit")
        b = dedupe_key("2026-01-15", 4.50, "x", "credit")
        assert a != b


def _seed(tid: str, **fields):
    base = {
        "transaction_id":   tid,
        "id":               tid,
        "date":             "2026-01-15",
        "amount":           4.50,
        "description":      "STARBUCKS",
        "transaction_type": "debit",
        "source":           "csv",
        "is_shared":        False,
        "reviewed":         False,
        "category":         None,
    }
    base.update(fields)
    state.stored_transactions[tid] = base


class TestDedupeEndpoint:
    def test_preview_groups_cross_source_duplicates(self, client):
        # Same purchase, same date/amount/direction, descriptions that differ
        # only in casing + punctuation → should collide on the dedupe key.
        _seed("csv_abc", source="barclays", description="STARBUCKS #1234")
        _seed("simplefin_xyz", source="simplefin", description="starbucks  1234")
        _seed("solo", description="UNRELATED")

        r = client.post("/api/transactions/dedupe", json={"mode": "preview"})
        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "preview"
        assert body["group_count"] == 1
        assert body["duplicate_count"] == 1
        # Original txns are untouched in preview.
        assert "csv_abc" in state.stored_transactions
        assert "simplefin_xyz" in state.stored_transactions

    def test_apply_keeps_reviewed_winner(self, client):
        _seed("loser_id", reviewed=False)
        _seed("winner_id", reviewed=True)

        r = client.post("/api/transactions/dedupe", json={"mode": "apply"})
        assert r.status_code == 200
        body = r.json()
        assert body["removed_count"] == 1
        assert body["removed_ids"] == ["loser_id"]
        assert "winner_id" in state.stored_transactions
        assert "loser_id" not in state.stored_transactions

    def test_apply_keeps_categorized_winner(self, client):
        _seed("loser_id")
        _seed("winner_id", category="restaurants")

        r = client.post("/api/transactions/dedupe", json={"mode": "apply"})
        assert r.status_code == 200
        assert r.json()["removed_ids"] == ["loser_id"]

    def test_apply_no_duplicates_is_noop(self, client):
        _seed("only_one")
        r = client.post("/api/transactions/dedupe", json={"mode": "apply"})
        assert r.status_code == 200
        assert r.json()["removed_count"] == 0
        assert "only_one" in state.stored_transactions

    def test_invalid_mode_rejected(self, client):
        r = client.post("/api/transactions/dedupe", json={"mode": "nuke"})
        assert r.status_code == 422


class TestDeleteTransaction:
    def test_delete_removes_txn(self, client):
        _seed("zap_me")
        r = client.delete("/api/transactions/zap_me")
        assert r.status_code == 204
        assert "zap_me" not in state.stored_transactions

    def test_delete_unknown_returns_404(self, client):
        r = client.delete("/api/transactions/does-not-exist")
        assert r.status_code == 404


class TestIngestSkipsCrossSourceDuplicate:
    def test_csv_upload_rejects_dupe_of_already_loaded_txn(self, client, sample_discover_csv):
        # Seed a txn that mirrors the first row of sample_discover_csv but with
        # a different transaction_id and a different source — exactly the case
        # transaction_id-based dedupe missed before.
        _seed(
            "simplefin_preexisting",
            date="01/15/2024",
            amount=4.50,
            description="STARBUCKS",
            transaction_type="debit",
            source="simplefin",
        )

        import io
        res = client.post(
            "/api/upload-csv",
            files={"file": ("d.csv", io.BytesIO(sample_discover_csv.encode("utf-8")), "text/csv")},
        )
        assert res.status_code == 200
        body = res.json()
        # 2 rows in CSV, 1 already exists by dedupe key → only 1 new.
        assert body["count"] == 1
        assert body["duplicates"] == 1