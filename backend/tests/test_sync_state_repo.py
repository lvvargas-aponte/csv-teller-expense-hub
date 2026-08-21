"""The sync bookkeeping tables: corrections feed, run log, per-row watermark."""
from db import sync_state_repo


class TestCorrections:
    def test_records_and_lists_unacknowledged(self):
        n = sync_state_repo.record_corrections(
            "2026-06",
            [
                {"txn_id": "u1:t1", "column_name": "Amount",
                 "sheet_value": "$9.99", "app_value": "12.50"},
                {"txn_id": "u1:t2", "column_name": "Notes",
                 "sheet_value": "typo", "app_value": ""},
            ],
        )
        assert n == 2

        rows = sync_state_repo.list_unacknowledged()
        assert len(rows) == 2
        assert {r["column_name"] for r in rows} == {"Amount", "Notes"}
        assert all(r["acknowledged_at"] is None for r in rows)
        assert all(r["period"] == "2026-06" for r in rows)

    def test_empty_list_is_a_noop(self):
        assert sync_state_repo.record_corrections("2026-06", []) == 0
        assert sync_state_repo.list_unacknowledged() == []

    def test_acknowledge_removes_from_the_feed_but_keeps_the_row(self):
        sync_state_repo.record_corrections(
            "2026-06",
            [{"txn_id": "u1:t1", "column_name": "Amount",
              "sheet_value": "$9.99", "app_value": "12.50"}],
        )
        cid = sync_state_repo.list_unacknowledged()[0]["id"]

        assert sync_state_repo.acknowledge(cid) is True
        assert sync_state_repo.list_unacknowledged() == []
        assert sync_state_repo.acknowledge(cid) is False


class TestRuns:
    def test_run_lifecycle(self):
        run_id = sync_state_repo.start_run("2026-06", "both")
        assert isinstance(run_id, int)

        open_run = sync_state_repo.last_run("2026-06")
        assert open_run["status"] == "running"
        assert open_run["finished_at"] is None

        sync_state_repo.finish_run(run_id, "ok", rows_pushed=3, rows_pulled=2, rows_deleted=1)

        done = sync_state_repo.last_run("2026-06")
        assert done["status"] == "ok"
        assert done["finished_at"] is not None
        assert (done["rows_pushed"], done["rows_pulled"], done["rows_deleted"]) == (3, 2, 1)

    def test_last_ok_run_skips_refusals(self):
        ok_id = sync_state_repo.start_run("2026-06", "both")
        sync_state_repo.finish_run(ok_id, "ok", rows_pushed=1)

        bad_id = sync_state_repo.start_run("2026-06", "both")
        sync_state_repo.finish_run(bad_id, "refused", refusal_reason="slot_collision")

        assert sync_state_repo.last_run("2026-06")["status"] == "refused"
        assert sync_state_repo.last_ok_run("2026-06")["id"] == ok_id


class TestRowState:
    def test_mark_synced_is_idempotent_and_advances_the_watermark(self):
        sync_state_repo.mark_synced("u1:t1", "t1", "2026-06")
        first = sync_state_repo.get_row_state("u1:t1")["sheet_synced_at"]

        sync_state_repo.mark_synced("u1:t1", "t1", "2026-06")
        second = sync_state_repo.get_row_state("u1:t1")["sheet_synced_at"]

        assert second >= first
        assert sync_state_repo.synced_at_map(["u1:t1"])["u1:t1"] == second

    def test_disputes_survive_a_later_mark_synced(self):
        """The peer owns the dispute columns; pushing our own row must not clear them."""
        sync_state_repo.mark_synced("u1:t1", "t1", "2026-06")
        sync_state_repo.set_disputes("u1:t1", "Y", "Christy", "this was mine")
        sync_state_repo.mark_synced("u1:t1", "t1", "2026-06")

        state = sync_state_repo.get_row_state("u1:t1")
        assert (state["dispute_flag"], state["dispute_by"]) == ("Y", "Christy")
        assert [d["txn_id"] for d in sync_state_repo.list_disputes_against_me()] == ["u1:t1"]

    def test_set_disputes_on_an_unknown_row_creates_it(self):
        sync_state_repo.set_disputes("u1:t9", "Y", "Christy", "?")
        assert sync_state_repo.get_row_state("u1:t9")["dispute_flag"] == "Y"

    def test_set_disputes_bulk_upserts_every_item(self):
        n = sync_state_repo.set_disputes_bulk(
            [
                {"txn_id": "u1:t1", "flag": "Y", "by": "Christy", "note": "wrong split"},
                {"txn_id": "u1:t2", "flag": None, "by": None, "note": None},
            ]
        )
        assert n == 2
        assert sync_state_repo.get_row_state("u1:t1")["dispute_flag"] == "Y"
        assert sync_state_repo.get_row_state("u1:t2")["dispute_flag"] is None

    def test_set_disputes_bulk_empty_list_is_a_noop(self):
        assert sync_state_repo.set_disputes_bulk([]) == 0

    def test_delete_row_state(self):
        sync_state_repo.mark_synced("u1:t1", "t1", "2026-06")
        assert sync_state_repo.delete_row_state(["u1:t1", "u1:absent"]) == 1
        assert sync_state_repo.get_row_state("u1:t1") is None


class TestTransactionsUpdatedAt:
    def test_reads_the_json_store_write_timestamp(self):
        """The only available 'the user edited this' signal — see the plan header."""
        import state

        state.stored_transactions["t1"] = {"description": "Coffee", "amount": 4.5}
        state.stored_transactions["t2"] = {"description": "Rent", "amount": 1200}

        stamps = sync_state_repo.transactions_updated_at(["t1", "t2", "missing"])
        assert set(stamps) == {"t1", "t2"}
        assert stamps["t2"] >= stamps["t1"]

    def test_empty_input(self):
        assert sync_state_repo.transactions_updated_at([]) == {}
