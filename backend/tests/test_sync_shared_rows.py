"""The combined view of both sides' shared rows for one month."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

import identity_service
import state
from db import identity_repo, peer_transactions_repo, sync_state_repo
from main import app
from sheet_sync import shared_view

P1, P2 = "Valeria", "Christy"
PEER_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def names(monkeypatch):
    monkeypatch.setattr(shared_view, "PERSON_1_NAME", P1)
    monkeypatch.setattr(shared_view, "PERSON_2_NAME", P2)


def mine(tid, **over):
    txn = {
        "date": "06/15/2026", "description": "Groceries", "amount": -112.25,
        "who": P1, "notes": "", "is_shared": True, "reviewed": True,
        "person_1_owes": 0.0, "person_2_owes": 56.13,
    }
    txn.update(over)
    state.stored_transactions[tid] = txn
    return txn


def theirs(txn_id=f"{PEER_ID}:x1", **over):
    row = {
        "txn_id": txn_id, "owner_user_id": PEER_ID, "date": "2026-06-02",
        "description": "Cleaning", "amount": 150, "who": P2,
        "person_1_owes": 75, "person_2_owes": 0, "notes": "",
        "reviewed": True, "settles_in_period": "2026-06",
    }
    row.update(over)
    peer_transactions_repo.upsert_many([row])
    return row


class TestShape:
    def test_returns_identity_and_period(self, client):
        identity_service.ensure_identity()
        body = client.get("/api/sync/shared-rows?period=2026-06").json()

        assert body["period"] == "2026-06"
        assert body["me"]["display_name"] == P1
        assert body["me"]["person_slot"] == 1

    def test_empty_month_returns_no_rows(self, client):
        identity_service.ensure_identity()
        assert client.get("/api/sync/shared-rows?period=2026-06").json()["rows"] == []


class TestOwnership:
    def test_your_row_and_their_row_appear_together_and_are_labelled(self, client):
        identity_service.ensure_identity()
        mine("t1")
        theirs()

        rows = client.get("/api/sync/shared-rows?period=2026-06").json()["rows"]

        assert {r["owner"] for r in rows} == {"me", "peer"}
        assert [r["description"] for r in rows] == ["Cleaning", "Groceries"]  # date order
        peer_row = next(r for r in rows if r["owner"] == "peer")
        assert peer_row["owner_name"] == P2

    def test_rows_from_another_month_are_excluded(self, client):
        identity_service.ensure_identity()
        mine("t1", date="07/04/2026")
        assert client.get("/api/sync/shared-rows?period=2026-06").json()["rows"] == []

    def test_owner_name_follows_a_rename_not_the_config_default(self, client):
        identity_service.ensure_identity()
        mine("t1")
        identity_repo.rename_identity("Val")

        row = client.get("/api/sync/shared-rows?period=2026-06").json()["rows"][0]

        assert row["owner_name"] == "Val"


class TestOwesResolvedBySlot:
    def test_when_you_paid_your_side_is_null_and_theirs_is_set(self, client):
        identity_service.ensure_identity()
        mine("t1", who=P1, person_1_owes=0.0, person_2_owes=56.13)

        row = client.get("/api/sync/shared-rows?period=2026-06").json()["rows"][0]

        assert row["you_owe"] is None
        assert row["they_owe"] == 56.13

    def test_when_they_paid_your_side_carries_the_amount(self, client):
        identity_service.ensure_identity()
        mine("t1", who=P2, person_1_owes=56.13, person_2_owes=0.0)

        row = client.get("/api/sync/shared-rows?period=2026-06").json()["rows"][0]

        assert row["you_owe"] == 56.13
        assert row["they_owe"] is None

    def test_a_peer_row_is_resolved_by_slot_too(self, client):
        identity_service.ensure_identity()
        theirs()

        row = client.get("/api/sync/shared-rows?period=2026-06").json()["rows"][0]

        assert row["you_owe"] == 75.0


class TestPublishability:
    def _reason(self, client):
        rows = client.get("/api/sync/shared-rows?period=2026-06").json()["rows"]
        return rows[0]["publishable"], rows[0]["blocked_reason"]

    def test_a_complete_row_is_publishable(self, client):
        identity_service.ensure_identity()
        mine("t1")
        assert self._reason(client) == (True, None)

    def test_an_unreviewed_row_is_still_publishable(self, client):
        """Reviewed is triage state, not a gate — see project_push's docstring."""
        identity_service.ensure_identity()
        mine("t1", reviewed=False)
        assert self._reason(client) == (True, None)

    def test_a_row_with_a_blank_who_is_publishable_as_ours(self, client):
        identity_service.ensure_identity()
        mine("t1", who="")
        assert self._reason(client) == (True, None)

    def test_a_row_with_no_split_is_flagged(self, client):
        """The rows sub-project B deliberately withholds must not be invisible."""
        identity_service.ensure_identity()
        mine("t1", who=P1, person_1_owes=0.0, person_2_owes=0.0)
        publishable, reason = self._reason(client)
        assert publishable is False and "split" in reason.lower()

    def test_a_row_with_an_unrecognised_who_is_flagged(self, client):
        identity_service.ensure_identity()
        mine("t1", who="Mom")
        publishable, reason = self._reason(client)
        assert publishable is False and "Mom" in reason

    def test_a_peer_row_is_always_publishable(self, client):
        identity_service.ensure_identity()
        theirs()
        assert self._reason(client) == (True, None)

    def test_when_who_and_date_are_both_bad_the_date_reason_wins(self, client):
        """project_push checks date before who — the page must report the same one."""
        identity_service.ensure_identity()
        # settles_in_period keeps the row in this month's list despite the bad
        # date — period_of falls back to parsing `date` otherwise, which would
        # exclude the row entirely rather than surface it as unpublishable.
        mine("t1", who="Mom", date="not-a-date", settles_in_period="2026-06")
        publishable, reason = self._reason(client)
        assert publishable is False
        assert "date" in reason.lower()
        assert "not-a-date" in reason

    def test_a_blank_owes_value_degrades_instead_of_500ing(self, client):
        identity_service.ensure_identity()
        mine("t1", who=P1, person_1_owes=0.0, person_2_owes="")
        res = client.get("/api/sync/shared-rows?period=2026-06")
        assert res.status_code == 200
        row = res.json()["rows"][0]
        assert row["publishable"] is False
        assert "split" in row["blocked_reason"].lower()


class TestDisputes:
    def test_a_dispute_against_your_row_is_shown(self, client):
        me = identity_service.ensure_identity()
        mine("t1")
        sync_state_repo.set_disputes(f"{me['user_id']}:t1", "Y", P2, "that was mine")

        row = client.get("/api/sync/shared-rows?period=2026-06").json()["rows"][0]

        assert row["dispute_flag"] == "Y"
        assert row["dispute_by"] == P2
        assert row["dispute_note"] == "that was mine"

    def test_a_dispute_you_raised_on_their_row_is_shown(self, client):
        identity_service.ensure_identity()
        theirs()
        peer_transactions_repo.set_dispute(f"{PEER_ID}:x1", "Y", P1, "not shared")

        row = client.get("/api/sync/shared-rows?period=2026-06").json()["rows"][0]

        assert row["dispute_flag"] == "Y"


class TestRoute:
    def test_a_malformed_period_is_422(self, client):
        assert client.get("/api/sync/shared-rows?period=June").status_code == 422

    def test_a_period_before_the_cutover_is_422(self, client):
        res = client.get("/api/sync/shared-rows?period=2026-05")
        assert res.status_code == 422
        assert "cutover" in res.json()["detail"].lower()


class TestNamePlumbing:
    """_my_row takes the person names as parameters; _peer_row must resolve
    slots from the SAME parameters, not from the shared_view module globals —
    otherwise a caller passing different names gets two different slot
    resolutions from one payload."""

    def test_peer_row_resolves_slot_from_the_passed_in_names_not_module_globals(
        self, monkeypatch
    ):
        monkeypatch.setattr(shared_view, "PERSON_1_NAME", "WrongName1")
        monkeypatch.setattr(shared_view, "PERSON_2_NAME", "WrongName2")

        peer_row = {
            "txn_id": f"{PEER_ID}:x1", "date": "2026-06-02",
            "description": "Cleaning", "amount": 150, "who": P2,
            "person_1_owes": 75, "person_2_owes": 0, "notes": "",
            "reviewed": True,
        }

        row = shared_view._peer_row(peer_row, my_slot=1, peer_name=P2,
                                     person_1_name=P1, person_2_name=P2)

        assert row["you_owe"] == 75.0


class TestRowMeta:
    def test_your_row_carries_its_category_and_account(self, client):
        identity_service.ensure_identity()
        mine("t1", category="groceries", institution="Chase Bank")

        row = client.get("/api/sync/shared-rows?period=2026-06").json()["rows"][0]

        assert row["category"] == "groceries"
        assert row["account"] == "Chase"  # normalized, as everywhere else

    def test_a_blank_category_or_account_is_null_not_a_dash(self, client):
        """The page omits empty meta rather than rendering a placeholder."""
        identity_service.ensure_identity()
        mine("t1", category="", institution="")

        row = client.get("/api/sync/shared-rows?period=2026-06").json()["rows"][0]

        assert row["category"] is None
        assert row["account"] is None

    def test_a_peer_row_reports_category_and_account_as_empty(self, client):
        """Both row shapes carry the same keys; a peer row simply has no
        account or category of ours to report."""
        identity_service.ensure_identity()
        theirs()

        row = client.get("/api/sync/shared-rows?period=2026-06").json()["rows"][0]

        assert row["category"] is None
        assert row["account"] is None


class TestSplitLabel:
    def _label(self, client):
        return client.get("/api/sync/shared-rows?period=2026-06").json()["rows"][0]["split_label"]

    def test_an_even_split_reads_fifty_fifty(self, client):
        identity_service.ensure_identity()
        mine("t1", amount=-112.26, who=P1, person_1_owes=0.0, person_2_owes=56.13)
        assert self._label(client) == "50 / 50 split"

    def test_an_uneven_split_reads_payer_share_first(self, client):
        identity_service.ensure_identity()
        mine("t1", amount=-100.0, who=P1, person_1_owes=0.0, person_2_owes=30.0)
        assert self._label(client) == "70 / 30 split"

    def test_a_row_with_no_split_has_no_label(self, client):
        identity_service.ensure_identity()
        mine("t1", who=P1, person_1_owes=0.0, person_2_owes=0.0)
        assert self._label(client) is None

    def test_a_peer_row_gets_a_label_from_the_same_helper(self, client):
        identity_service.ensure_identity()
        theirs(amount=150, who=P2, person_1_owes=75, person_2_owes=0)
        assert self._label(client) == "50 / 50 split"


class TestSettlement:
    def _settlement(self, client):
        return client.get("/api/sync/shared-rows?period=2026-06").json()["settlement"]

    def test_when_they_owe_more_the_net_points_at_them(self, client):
        identity_service.ensure_identity()
        mine("t1", amount=-200.0, who=P1, person_1_owes=0.0, person_2_owes=100.0)
        mine("t2", amount=-40.0, who=P2, person_1_owes=20.0, person_2_owes=0.0)

        s = self._settlement(client)

        assert s["they_owe_total"] == 100.0
        assert s["you_owe_total"] == 20.0
        assert s["net"] == 80.0
        assert s["direction"] == "they_owe"

    def test_when_you_owe_more_the_net_points_at_you(self, client):
        identity_service.ensure_identity()
        mine("t1", amount=-40.0, who=P1, person_1_owes=0.0, person_2_owes=20.0)
        mine("t2", amount=-200.0, who=P2, person_1_owes=100.0, person_2_owes=0.0)

        s = self._settlement(client)

        assert s["net"] == 80.0
        assert s["direction"] == "you_owe"

    def test_equal_owes_settle_even_with_a_zero_net(self, client):
        identity_service.ensure_identity()
        mine("t1", amount=-100.0, who=P1, person_1_owes=0.0, person_2_owes=50.0)
        mine("t2", amount=-100.0, who=P2, person_1_owes=50.0, person_2_owes=0.0)

        s = self._settlement(client)

        assert s["net"] == 0.0
        assert s["direction"] == "even"

    def test_counted_totals_describe_only_the_publishable_rows(self, client):
        identity_service.ensure_identity()
        mine("t1", amount=-200.0, who=P1, person_1_owes=0.0, person_2_owes=100.0)
        mine("t2", amount=-500.0, who=P1, person_1_owes=0.0, person_2_owes=0.0)

        s = self._settlement(client)

        assert s["counted_count"] == 1
        assert s["counted_amount"] == 200.0
        assert s["blocked_count"] == 1

    def test_a_blocked_row_never_moves_the_net(self, client):
        """A row sync would withhold must not be promised to either side."""
        identity_service.ensure_identity()
        mine("t1", amount=-200.0, who="Mom", person_1_owes=0.0, person_2_owes=100.0)

        s = self._settlement(client)

        assert s["they_owe_total"] == 0.0
        assert s["you_owe_total"] == 0.0
        assert s["net"] == 0.0
        assert s["direction"] == "even"
        assert s["blocked_count"] == 1

    def test_an_empty_month_settles_even_at_zero(self, client):
        identity_service.ensure_identity()
        s = self._settlement(client)
        assert s == {
            "you_owe_total": 0.0, "they_owe_total": 0.0, "net": 0.0,
            "direction": "even", "counted_count": 0, "counted_amount": 0.0,
            "blocked_count": 0,
        }


class TestRepairableBlockedRows:
    """A blocked row of ours carries what the page needs to repair it here."""

    def _row(self, client, **over):
        mine("t1", **over)
        rows = client.get("/api/sync/shared-rows?period=2026-06").json()["rows"]
        return next(r for r in rows if r["transaction_id"] == "t1")

    def test_a_missing_split_is_kinded_so_the_page_can_offer_the_editor(self, client):
        row = self._row(client, person_1_owes=0, person_2_owes=0)

        assert row["publishable"] is False
        assert row["blocked_kind"] == "split"

    def test_an_unrecognised_payer_is_kinded(self, client):
        row = self._row(client, who="Mom")

        assert row["blocked_kind"] == "who"

    def test_an_unreadable_date_is_kinded_and_listed_on_the_current_month(self, client):
        # It belongs to no month, so it is surfaced on the current one rather
        # than being invisible on every page that could report the problem.
        mine("t1", date="not-a-date")
        this_month = date.today().strftime("%Y-%m")

        rows = client.get(f"/api/sync/shared-rows?period={this_month}").json()["rows"]
        row = next(r for r in rows if r["transaction_id"] == "t1")

        assert row["blocked_kind"] == "date"

    def test_an_undated_row_is_not_repeated_on_other_months(self, client):
        mine("t1", date="not-a-date")

        rows = client.get("/api/sync/shared-rows?period=2026-06").json()["rows"]

        assert [r["transaction_id"] for r in rows] == []

    def test_an_unreadable_amount_is_kinded(self, client):
        row = self._row(client, amount="lots")

        assert row["blocked_kind"] == "amount"

    def test_a_publishable_row_has_no_kind(self, client):
        row = self._row(client)

        assert row["publishable"] is True
        assert row["blocked_kind"] is None

    def test_our_row_carries_the_raw_fields_the_editor_writes_back(self, client):
        row = self._row(client, person_1_owes=0, person_2_owes=0)

        assert row["editable"] == {
            "is_shared": True,
            "what": "",
            "person_1_owes": 0,
            "person_2_owes": 0,
            "raw_date": "06/15/2026",
            "raw_amount": -112.25,
        }

    def test_a_peer_row_is_not_editable_from_here(self, client):
        theirs()
        rows = client.get("/api/sync/shared-rows?period=2026-06").json()["rows"]
        peer_row = next(r for r in rows if r["owner"] == "peer")

        # It lives on their instance; offering an editor would write nothing.
        assert peer_row["editable"] is None
        assert peer_row["blocked_kind"] is None


class TestFixingABlockedRowInPlace:
    """The repair goes through PUT /transactions/{id} and unblocks the row."""

    def _rows(self, client):
        return client.get("/api/sync/shared-rows?period=2026-06").json()

    def _put(self, client, **patch):
        body = {
            "is_shared": True, "who": P1, "what": "", "notes": "",
            "person_1_owes": 0, "person_2_owes": 0, "reviewed": False,
        }
        body.update(patch)
        return client.put("/api/transactions/t1", json=body)

    def test_setting_a_split_unblocks_the_row_and_moves_the_net(self, client):
        mine("t1", person_1_owes=0, person_2_owes=0)
        assert self._rows(client)["settlement"]["net"] == 0

        assert self._put(client, person_2_owes=56.13).status_code == 200

        body = self._rows(client)
        row = next(r for r in body["rows"] if r["transaction_id"] == "t1")
        assert row["publishable"] is True
        assert row["blocked_kind"] is None
        assert body["settlement"]["net"] == 56.13

    def test_fixing_the_payer_unblocks_the_row(self, client):
        mine("t1", who="Mom")
        assert self._rows(client)["rows"][0]["blocked_kind"] == "who"

        assert self._put(client, who=P1, person_2_owes=56.13).status_code == 200

        assert self._rows(client)["rows"][0]["publishable"] is True

    def test_fixing_the_date_is_stored_in_the_apps_own_format(self, client):
        mine("t1", date="not-a-date")

        assert self._put(client, date="2026-06-11", person_2_owes=56.13).status_code == 200

        # Repairing the date is what files it under a month at all.
        row = self._rows(client)["rows"][0]
        assert row["publishable"] is True
        assert row["date"] == "2026-06-11"
        assert row["editable"]["raw_date"] == "06/11/2026"

    def test_a_date_that_still_cannot_be_read_is_refused(self, client):
        mine("t1", date="not-a-date")

        response = self._put(client, date="still nonsense")

        assert response.status_code == 422
        # The stored value is untouched, so the row keeps reporting the problem.
        this_month = date.today().strftime("%Y-%m")
        rows = client.get(f"/api/sync/shared-rows?period={this_month}").json()["rows"]
        assert rows[0]["blocked_kind"] == "date"

    def test_fixing_the_amount_unblocks_the_row(self, client):
        mine("t1", amount="lots")
        assert self._rows(client)["rows"][0]["blocked_kind"] == "amount"

        assert self._put(client, amount=-112.25, person_2_owes=56.13).status_code == 200

        row = self._rows(client)["rows"][0]
        assert row["publishable"] is True
        assert row["amount"] == -112.25

    def test_omitting_date_and_amount_leaves_them_untouched(self, client):
        # Every existing caller sends neither; they must stay no-ops.
        mine("t1")

        assert self._put(client, person_2_owes=56.13).status_code == 200

        row = self._rows(client)["rows"][0]
        assert row["editable"]["raw_date"] == "06/15/2026"
        assert row["amount"] == -112.25
