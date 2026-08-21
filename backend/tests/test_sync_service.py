"""End-to-end sync against an in-memory spreadsheet with a real database."""
from datetime import date

import pytest

import identity_service
import state
from db import identity_repo, peer_transactions_repo, sync_state_repo
from sheet_sync import adoption, service, sync_sheet
from sheet_sync.gateway import InMemoryGateway
from sheet_sync.guards import Claim

P1, P2 = "Valeria", "Christy"
PEER_ID = "22222222-2222-2222-2222-222222222222"

HEADERS = [
    "Transaction Date", "Description", "Amount", "Who",
    f"What {P1} Owes", f"What {P2} Owes", "Notes", "Reviewed",
    "Dispute", "Dispute By", "Dispute Note", "Txn ID", "Owner", "Carried From",
]


@pytest.fixture(autouse=True)
def person_names(monkeypatch):
    """service reads these as module globals at call time and passes them down."""
    monkeypatch.setattr(service, "PERSON_1_NAME", P1)
    monkeypatch.setattr(service, "PERSON_2_NAME", P2)


@pytest.fixture
def me():
    return identity_service.ensure_identity()


@pytest.fixture
def gateway():
    return InMemoryGateway({"June 2026": [list(HEADERS)]})


def add_txn(tid, **over):
    txn = {
        "date": "06/15/2026",
        "description": "Groceries",
        "amount": -112.25,
        "who": P1,
        "notes": "",
        "is_shared": True,
        "reviewed": True,
        "person_1_owes": 56.13,
        "person_2_owes": 56.13,
    }
    txn.update(over)
    state.stored_transactions[tid] = txn
    return txn


def peer_claim(**over):
    base = dict(
        user_id=PEER_ID, display_name=P2, person_slot=2,
        contract_version="1.0", person_1_name=P1, person_2_name=P2,
    )
    base.update(over)
    return Claim(**base)


def edit_sheet(gateway, row_number, header, value):
    """InMemoryGateway.read_rows returns a deepcopy — a test that mutates its
    result changes nothing. Hand edits must target the gateway's own data."""
    gateway.data["June 2026"][row_number - 1][HEADERS.index(header)] = value


def peer_row(txn_id=f"{PEER_ID}:x1", **over):
    values = {
        "Transaction Date": "6/2/2026", "Description": "Cleaning",
        "Amount": "$150.00", "Who": P2, f"What {P1} Owes": "$75.00",
        f"What {P2} Owes": "", "Notes": "", "Reviewed": "TRUE",
        "Dispute": "", "Dispute By": "", "Dispute Note": "",
        "Txn ID": txn_id, "Owner": PEER_ID, "Carried From": "",
    }
    values.update(over)
    return [values[h] for h in HEADERS]


class TestOpenPeriods:
    def test_starts_at_the_cutover(self):
        assert service.open_periods(date(2026, 6, 10)) == ["2026-06"]

    def test_includes_every_month_since(self):
        assert service.open_periods(date(2026, 8, 17)) == ["2026-06", "2026-07", "2026-08"]

    def test_never_reaches_before_the_cutover(self):
        assert service.open_periods(date(2026, 4, 1)) == []


class TestPush:
    def test_appends_a_reviewed_shared_transaction(self, me, gateway):
        add_txn("t1")
        out = service.sync_period(gateway, "2026-06")

        assert out.status == "ok"
        assert out.rows_pushed == 1

        row = gateway.read_rows("June 2026")[1]
        assert row[HEADERS.index("Txn ID")] == f"{me['user_id']}:t1"
        assert row[HEADERS.index("Owner")] == me["user_id"]
        assert row[HEADERS.index("Who")] == P1
        assert row[HEADERS.index(f"What {P1} Owes")] == ""
        assert row[HEADERS.index(f"What {P2} Owes")] == "56.13"

    def test_running_twice_changes_nothing(self, me, gateway):
        add_txn("t1")
        service.sync_period(gateway, "2026-06")
        before = gateway.read_rows("June 2026")

        second = service.sync_period(gateway, "2026-06")

        assert gateway.read_rows("June 2026") == before
        assert second.rows_pushed == 0
        assert second.corrections == []

    def test_unsharing_deletes_the_row(self, me, gateway):
        add_txn("t1")
        add_txn("t2", description="Fuel")
        service.sync_period(gateway, "2026-06")

        t = state.stored_transactions["t1"]
        t["is_shared"] = False
        state.stored_transactions["t1"] = t

        out = service.sync_period(gateway, "2026-06")

        assert out.rows_deleted == 1
        remaining = [r[HEADERS.index("Description")] for r in gateway.read_rows("June 2026")[1:]]
        assert remaining == ["Fuel"]

    def test_never_writes_a_row_it_does_not_own(self, me, gateway):
        gateway.append_rows("June 2026", [peer_row()])
        add_txn("t1")

        service.sync_period(gateway, "2026-06")

        peer = gateway.read_rows("June 2026")[1]
        assert peer[HEADERS.index("Description")] == "Cleaning"
        assert peer[HEADERS.index("Owner")] == PEER_ID

    def test_an_unpublishable_row_is_reported_not_guessed(self, me, gateway):
        add_txn("t1", who="Mom")
        out = service.sync_period(gateway, "2026-06")

        assert out.rows_pushed == 0
        assert out.unpublishable[0]["transaction_id"] == "t1"

    def test_dry_run_writes_nothing(self, me, gateway):
        add_txn("t1")
        out = service.sync_period(gateway, "2026-06", dry_run=True)

        assert out.rows_pushed == 1
        assert len(gateway.read_rows("June 2026")) == 1
        assert sync_state_repo.get_row_state(f"{me['user_id']}:t1") is None

    def test_dry_run_does_not_create_a_worksheet(self, me, gateway):
        add_txn("t1", date="08/03/2026")
        out = service.sync_period(gateway, "2026-08", dry_run=True)

        assert out.status == "ok"
        assert out.rows_pushed == 1
        assert "August 2026" not in gateway.list_worksheets()

    def test_dry_run_writes_no_claim_row(self, me, gateway):
        add_txn("t1")
        service.sync_period(gateway, "2026-06", dry_run=True)

        assert sync_sheet.read_claims(gateway) == []

    def test_dry_run_does_not_adopt_peers_or_import_rows(self, me, gateway):
        sync_sheet.write_claim(gateway, peer_claim())
        gateway.append_rows("June 2026", [peer_row()])
        add_txn("t1")

        out = service.sync_period(gateway, "2026-06", dry_run=True)

        assert out.rows_pushed == 1
        assert out.rows_pulled == 1
        assert peer_transactions_repo.get(f"{PEER_ID}:x1") is None
        assert identity_repo.list_peers()[0]["user_id"] != PEER_ID


class TestCorrections:
    def test_a_hand_edit_is_restored_and_surfaced(self, me, gateway):
        add_txn("t1")
        service.sync_period(gateway, "2026-06")

        edit_sheet(gateway, 2, "Amount", "9.99")

        out = service.sync_period(gateway, "2026-06")

        assert gateway.read_rows("June 2026")[1][HEADERS.index("Amount")] == "112.25"
        assert out.corrections[0]["column_name"] == "Amount"
        assert out.corrections[0]["sheet_value"] == "9.99"

        feed = sync_state_repo.list_unacknowledged()
        assert [c["column_name"] for c in feed] == ["Amount"]

    def test_our_own_later_edit_is_not_a_correction(self, me, gateway):
        """Overwriting the sheet with a change the user made in the app is
        the system working, not a hand edit to warn about."""
        add_txn("t1")
        service.sync_period(gateway, "2026-06")

        t = state.stored_transactions["t1"]
        t["amount"] = -200.00
        state.stored_transactions["t1"] = t

        out = service.sync_period(gateway, "2026-06")

        assert gateway.read_rows("June 2026")[1][HEADERS.index("Amount")] == "200.00"
        assert out.corrections == []
        assert sync_state_repo.list_unacknowledged() == []

    def test_the_first_push_is_not_a_correction(self, me, gateway):
        add_txn("t1")
        out = service.sync_period(gateway, "2026-06")

        assert out.corrections == []

    def test_a_formatting_round_trip_is_not_a_correction(self, me, gateway):
        """Sheets re-renders 112.25 as $112.25 and 06/15/2026 as 6/15/2026."""
        add_txn("t1")
        service.sync_period(gateway, "2026-06")

        edit_sheet(gateway, 2, "Amount", "$112.25")
        edit_sheet(gateway, 2, "Transaction Date", "6/15/2026")

        out = service.sync_period(gateway, "2026-06")

        assert out.corrections == []
        assert sync_state_repo.list_unacknowledged() == []


class TestPull:
    def test_imports_the_peers_rows(self, me, gateway):
        sync_sheet.write_claim(gateway, peer_claim())
        gateway.append_rows("June 2026", [peer_row()])

        out = service.sync_period(gateway, "2026-06")

        assert out.rows_pulled == 1
        imported = peer_transactions_repo.get(f"{PEER_ID}:x1")
        assert imported["description"] == "Cleaning"
        assert imported["settles_in_period"] == "2026-06"

    def test_learns_the_peers_real_user_id_from_their_claim(self, me, gateway):
        """Sub-project A's PF-5: bootstrap invented a placeholder id."""
        placeholder = identity_repo.list_peers()[0]["user_id"]
        assert placeholder != PEER_ID

        sync_sheet.write_claim(gateway, peer_claim())
        service.sync_period(gateway, "2026-06")

        peers = identity_repo.list_peers()
        assert len(peers) == 1
        assert peers[0]["user_id"] == PEER_ID

    def test_a_dispute_against_our_row_is_recorded_locally(self, me, gateway):
        add_txn("t1")
        service.sync_period(gateway, "2026-06")

        edit_sheet(gateway, 2, "Dispute", "Y")
        edit_sheet(gateway, 2, "Dispute By", P2)
        edit_sheet(gateway, 2, "Dispute Note", "that was mine")

        service.sync_period(gateway, "2026-06")

        state_row = sync_state_repo.get_row_state(f"{me['user_id']}:t1")
        assert (state_row["dispute_flag"], state_row["dispute_by"]) == ("Y", P2)

    def test_pushing_our_row_again_does_not_clear_the_dispute(self, me, gateway):
        add_txn("t1")
        service.sync_period(gateway, "2026-06")
        edit_sheet(gateway, 2, "Dispute", "Y")
        edit_sheet(gateway, 2, "Dispute By", P2)
        service.sync_period(gateway, "2026-06")

        service.sync_period(gateway, "2026-06")

        assert gateway.read_rows("June 2026")[1][HEADERS.index("Dispute")] == "Y"
        assert sync_state_repo.get_row_state(f"{me['user_id']}:t1")["dispute_flag"] == "Y"

    def test_a_row_without_a_date_is_skipped_not_fatal(self, me, gateway):
        sync_sheet.write_claim(gateway, peer_claim())
        gateway.append_rows("June 2026", [peer_row(**{"Transaction Date": ""})])

        out = service.sync_period(gateway, "2026-06")

        assert out.status == "ok"
        assert out.rows_pulled == 0
        assert out.skipped_peer_rows == 1

    def test_a_true_dispute_cell_maps_to_y_without_erroring(self, me, gateway):
        """Dispute cells share the contract's truthy set with Reviewed, so a
        hand-written 'TRUE' must not violate sync_row_state's Y/N constraint."""
        add_txn("t1")
        service.sync_period(gateway, "2026-06")

        edit_sheet(gateway, 2, "Dispute", "TRUE")
        edit_sheet(gateway, 2, "Dispute By", P2)

        out = service.sync_period(gateway, "2026-06")

        assert out.status == "ok"
        state_row = sync_state_repo.get_row_state(f"{me['user_id']}:t1")
        assert state_row["dispute_flag"] == "Y"

    def test_an_explicit_n_dispute_cell_maps_to_n(self, me, gateway):
        add_txn("t1")
        service.sync_period(gateway, "2026-06")

        edit_sheet(gateway, 2, "Dispute", "N")

        out = service.sync_period(gateway, "2026-06")

        assert out.status == "ok"
        state_row = sync_state_repo.get_row_state(f"{me['user_id']}:t1")
        assert state_row["dispute_flag"] == "N"


class TestOutboundDispute:
    """The other half of the round-trip: raising, editing, clearing a dispute
    on a peer row, and having it reach the sheet's I–K columns."""

    def _import_peer_row(self, gateway):
        sync_sheet.write_claim(gateway, peer_claim())
        gateway.append_rows("June 2026", [peer_row()])
        service.sync_period(gateway, "2026-06")

    def test_a_local_dispute_reaches_the_sheet(self, me, gateway):
        self._import_peer_row(gateway)
        peer_transactions_repo.set_dispute(f"{PEER_ID}:x1", "Y", P1, "should be 70/30")

        out = service.sync_period(gateway, "2026-06")

        row = gateway.read_rows("June 2026")[1]
        assert row[HEADERS.index("Dispute")] == "Y"
        assert row[HEADERS.index("Dispute By")] == P1
        assert row[HEADERS.index("Dispute Note")] == "should be 70/30"
        assert out.disputes_pushed == 1
        assert out.rows_pushed == 0, (
            "a dispute write must never inflate rows_pushed — that count is "
            "computed before the dispute updates are merged into the plan"
        )

    def test_clearing_blanks_the_sheet_cells(self, me, gateway):
        self._import_peer_row(gateway)
        txn_id = f"{PEER_ID}:x1"
        peer_transactions_repo.set_dispute(txn_id, "Y", P1, "should be 70/30")
        service.sync_period(gateway, "2026-06")

        peer_transactions_repo.set_dispute(txn_id, None, None, None)
        out = service.sync_period(gateway, "2026-06")

        row = gateway.read_rows("June 2026")[1]
        assert row[HEADERS.index("Dispute")] == ""
        assert row[HEADERS.index("Dispute By")] == ""
        assert row[HEADERS.index("Dispute Note")] == ""
        assert out.disputes_pushed == 1

    def test_an_unchanged_cycle_writes_nothing(self, me, gateway):
        self._import_peer_row(gateway)
        peer_transactions_repo.set_dispute(f"{PEER_ID}:x1", "Y", P1, "should be 70/30")
        service.sync_period(gateway, "2026-06")
        before = gateway.read_rows("June 2026")

        out = service.sync_period(gateway, "2026-06")

        assert gateway.read_rows("June 2026") == before
        assert out.disputes_pushed == 0

    def test_never_writes_a_dispute_onto_a_row_it_owns(self, me, gateway):
        """The safety property that matters most: our own row is never a
        target, even if something upstream mistakenly produced a
        DesiredDispute naming it — e.g. a stray row in
        ``peer_shared_transactions`` keyed by our own txn_id."""
        add_txn("t1")
        service.sync_period(gateway, "2026-06")
        my_txn_id = f"{me['user_id']}:t1"

        peer_transactions_repo.upsert_many([{
            "txn_id": my_txn_id,
            "owner_user_id": me["user_id"],
            "date": "2026-06-15",
            "description": "Groceries",
            "amount": 112.25,
            "who": P1,
            "person_1_owes": 56.13,
            "person_2_owes": 56.13,
            "notes": "",
            "reviewed": True,
            "payer_user_id": me["user_id"],
            "carried_from_period": None,
            "settles_in_period": "2026-06",
        }])
        peer_transactions_repo.set_dispute(my_txn_id, "Y", P2, "not real")

        out = service.sync_period(gateway, "2026-06")

        row = gateway.read_rows("June 2026")[1]
        assert row[HEADERS.index("Dispute")] == ""
        assert row[HEADERS.index("Dispute By")] == ""
        assert row[HEADERS.index("Dispute Note")] == ""
        assert out.disputes_pushed == 0

    def test_a_deletion_and_a_dispute_write_in_the_same_cycle_do_not_misdirect(self, me, gateway):
        """apply_push must write updates — including dispute writes — before
        it deletes, against the pre-write row numbers (applier.py:3-7). Put a
        row we are about to delete BEFORE the peer row we are disputing, so
        that deleting first (the wrong order) would renumber the peer row out
        from under the dispute write and this test would fail."""
        add_txn("t1")
        add_txn("t2", description="Fuel")
        sync_sheet.write_claim(gateway, peer_claim())
        service.sync_period(gateway, "2026-06")

        gateway.append_rows("June 2026", [peer_row()])
        service.sync_period(gateway, "2026-06")

        rows = gateway.read_rows("June 2026")
        assert rows[1][HEADERS.index("Description")] == "Groceries"
        assert rows[3][HEADERS.index("Txn ID")] == f"{PEER_ID}:x1"

        peer_transactions_repo.set_dispute(f"{PEER_ID}:x1", "Y", P1, "should be 70/30")
        t = state.stored_transactions["t1"]
        t["is_shared"] = False
        state.stored_transactions["t1"] = t

        out = service.sync_period(gateway, "2026-06")

        assert out.status == "ok"
        assert out.rows_deleted == 1
        assert out.disputes_pushed == 1

        final_rows = gateway.read_rows("June 2026")
        assert len(final_rows) == 3
        descriptions = [r[HEADERS.index("Description")] for r in final_rows[1:]]
        assert "Groceries" not in descriptions

        peer_final = next(
            r for r in final_rows if r[HEADERS.index("Txn ID")] == f"{PEER_ID}:x1"
        )
        assert peer_final[HEADERS.index("Dispute")] == "Y"
        assert peer_final[HEADERS.index("Dispute By")] == P1
        assert peer_final[HEADERS.index("Dispute Note")] == "should be 70/30"

    def test_a_peer_raised_dispute_clears_locally_when_they_blank_it(self, me, gateway):
        add_txn("t1")
        service.sync_period(gateway, "2026-06")
        edit_sheet(gateway, 2, "Dispute", "Y")
        edit_sheet(gateway, 2, "Dispute By", P2)
        edit_sheet(gateway, 2, "Dispute Note", "wrong split")
        service.sync_period(gateway, "2026-06")
        assert sync_state_repo.get_row_state(f"{me['user_id']}:t1")["dispute_flag"] == "Y"

        edit_sheet(gateway, 2, "Dispute", "")
        edit_sheet(gateway, 2, "Dispute By", "")
        edit_sheet(gateway, 2, "Dispute Note", "")
        service.sync_period(gateway, "2026-06")

        state_row = sync_state_repo.get_row_state(f"{me['user_id']}:t1")
        assert state_row["dispute_flag"] is None
        assert state_row["dispute_by"] is None


class TestRefusals:
    def _assert_refused(self, out, reason, gateway):
        assert out.status == "refused"
        assert out.refusal_reason == reason
        assert out.rows_pushed == 0
        assert len(gateway.read_rows("June 2026")) == 1

    def test_contract_version_mismatch(self, me, gateway):
        add_txn("t1")
        sync_sheet.write_claim(gateway, peer_claim(contract_version="9.9"))

        self._assert_refused(service.sync_period(gateway, "2026-06"), "contract_version", gateway)

    def test_person_name_mismatch(self, me, gateway):
        add_txn("t1")
        sync_sheet.write_claim(gateway, peer_claim(person_2_name="Christina"))

        out = service.sync_period(gateway, "2026-06")
        self._assert_refused(out, "person_names", gateway)
        assert "Christina" in out.refusal_message

    def test_slot_collision(self, me, gateway):
        add_txn("t1")
        sync_sheet.write_claim(gateway, peer_claim(person_slot=1))

        self._assert_refused(service.sync_period(gateway, "2026-06"), "slot_collision", gateway)

    def test_duplicate_txn_id(self, me, gateway):
        add_txn("t1")
        gateway.append_rows("June 2026", [peer_row(), peer_row()])

        out = service.sync_period(gateway, "2026-06")
        assert out.status == "refused"
        assert out.refusal_reason == "duplicate_txn_id"
        assert out.rows_pushed == 0

    def test_a_refusal_writes_no_claim_row(self, me, gateway):
        add_txn("t1")
        sync_sheet.write_claim(gateway, peer_claim(contract_version="9.9"))

        service.sync_period(gateway, "2026-06")

        assert [c.user_id for c in sync_sheet.read_claims(gateway)] == [PEER_ID]

    def test_a_refusal_is_recorded_in_the_run_log(self, me, gateway):
        sync_sheet.write_claim(gateway, peer_claim(person_slot=1))
        service.sync_period(gateway, "2026-06")

        run = sync_state_repo.last_run("2026-06")
        assert run["status"] == "refused"
        assert run["refusal_reason"] == "slot_collision"


class TestWorksheetLifecycle:
    def test_an_empty_month_does_not_conjure_a_tab(self, me, gateway):
        out = service.sync_period(gateway, "2026-08")

        assert out.status == "ok"
        assert "August 2026" not in gateway.list_worksheets()

    def test_a_month_with_something_to_push_is_created_from_the_latest(self, me, gateway):
        add_txn("t1", date="08/03/2026")
        out = service.sync_period(gateway, "2026-08")

        assert "August 2026" in gateway.list_worksheets()
        assert gateway.read_rows("August 2026")[0] == HEADERS
        assert out.rows_pushed == 1


class TestFailureBehaviour:
    def test_a_failed_write_leaves_local_state_untouched(self, me, gateway):
        add_txn("t1")

        def boom(*a, **kw):
            raise RuntimeError("Google is over quota")

        gateway.append_rows = boom
        out = service.sync_period(gateway, "2026-06")

        assert out.status == "error"
        assert sync_state_repo.get_row_state(f"{me['user_id']}:t1") is None
        assert sync_state_repo.last_run("2026-06")["status"] == "error"

    def test_a_failed_write_zeroes_disputes_pushed_too(self, me, gateway):
        """Every other counter is deliberately zeroed on the error path so a
        failed run cannot over-report; disputes_pushed is the only visibility
        into the code that writes to the peer's row and was missed."""
        sync_sheet.write_claim(gateway, peer_claim())
        gateway.append_rows("June 2026", [peer_row()])
        service.sync_period(gateway, "2026-06")
        peer_transactions_repo.set_dispute(f"{PEER_ID}:x1", "Y", P1, "should be 70/30")

        real_write_cells = gateway.write_cells

        def boom(title, updates):
            if title == "June 2026":
                raise RuntimeError("Google is over quota")
            return real_write_cells(title, updates)

        gateway.write_cells = boom
        out = service.sync_period(gateway, "2026-06")

        assert out.status == "error"
        assert out.disputes_pushed == 0

    def test_the_next_run_repairs_it(self, me, gateway):
        add_txn("t1")
        broken, gateway.append_rows = gateway.append_rows, lambda *a, **kw: 1 / 0
        service.sync_period(gateway, "2026-06")
        gateway.append_rows = broken

        out = service.sync_period(gateway, "2026-06")

        assert out.status == "ok"
        assert out.rows_pushed == 1


class TestConvergence:
    def test_two_instances_agree_on_the_month(self, me, gateway):
        """One fake spreadsheet, both instances' rows, no cell contended."""
        add_txn("t1")
        sync_sheet.write_claim(gateway, peer_claim())
        gateway.append_rows("June 2026", [peer_row()])

        service.sync_period(gateway, "2026-06")
        service.sync_period(gateway, "2026-06")

        rows = gateway.read_rows("June 2026")[1:]
        owners = {r[HEADERS.index("Owner")] for r in rows}
        assert owners == {me["user_id"], PEER_ID}
        assert len(rows) == 2
        assert len(peer_transactions_repo.list_for_period("2026-06")) == 1


class TestAdoptionSeam:
    """The seam between adoption.py and service.py — nothing else crosses it.

    Adoption mints synthetic ids for sheet rows with no local counterpart
    (Phone Bill, Cleaning — genuinely manual, never coming from a bank feed).
    A sync cycle must never read that absence as "no longer shared" and
    delete the row it exists to preserve.
    """

    LEGACY_HEADERS = [
        "Transaction Date", "Description", "Amount", "Who",
        f"What {P1} Owes", f"What {P2} Owes", "Notes",
    ]

    def test_an_adopted_row_survives_the_next_sync(self, me):
        gateway = InMemoryGateway({
            "June 2026": [
                list(self.LEGACY_HEADERS),
                ["6/1/2026", "Phone Bill", "$112.25", P1, "", "", ""],
            ]
        })

        plan = adoption.plan_adoption(
            gateway, "2026-06", {1: me["user_id"]}, P1, P2, []
        )
        assert plan.rows and plan.rows[0].manual_only is True
        adoption.apply_adoption(gateway, plan)

        out = service.sync_period(gateway, "2026-06")

        assert out.status == "ok"
        assert out.rows_deleted == 0
        rows = gateway.read_rows("June 2026")[1:]
        descriptions = [r[self.LEGACY_HEADERS.index("Description")] for r in rows]
        assert "Phone Bill" in descriptions


class TestBuildGateway:
    """SHEET_SYNC_ENABLED / SPREADSHEET_ID are the only guard against a real
    write. Neither test ever sets the flag true against real credentials —
    both monkeypatch the module globals service.py already reads them from."""

    def test_disabled_flag_raises(self, monkeypatch):
        monkeypatch.setattr(service, "SHEET_SYNC_ENABLED", False)

        with pytest.raises(service.SyncDisabled):
            service.build_gateway()

    def test_enabled_but_no_spreadsheet_id_raises(self, monkeypatch):
        monkeypatch.setattr(service, "SHEET_SYNC_ENABLED", True)
        monkeypatch.setattr(service, "SPREADSHEET_ID", None)

        with pytest.raises(service.SyncDisabled):
            service.build_gateway()


class TestStatus:
    def test_status_shape(self, me, monkeypatch):
        monkeypatch.setattr(service, "SHEET_SYNC_ENABLED", False)
        out = service.status()

        assert set(out.keys()) == {
            "enabled", "open_periods", "last_run", "last_successful_pull",
            "publishable_rows", "refusal", "corrections", "disputes_against_me",
        }
        assert out["enabled"] is False
        assert isinstance(out["open_periods"], list)
        assert out["last_run"] is None
        assert out["last_successful_pull"] is None
        assert out["publishable_rows"] == 0
        assert out["refusal"] is None
        assert out["corrections"] == []
        assert out["disputes_against_me"] == []

    def test_status_reports_enabled_true_when_the_flag_is_on(self, me, monkeypatch):
        monkeypatch.setattr(service, "SHEET_SYNC_ENABLED", True)
        assert service.status()["enabled"] is True

    def test_a_refusal_includes_a_readable_message_not_just_the_code(self, me, gateway):
        sync_sheet.write_claim(gateway, peer_claim(person_slot=1))
        service.sync_period(gateway, "2026-06")

        refusal = service.status()["refusal"]

        assert refusal["reason"] == "slot_collision"
        assert refusal["message"] != refusal["reason"]
        assert len(refusal["message"]) > len("slot_collision")
