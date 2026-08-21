"""Publishability parity between the display page and the sync engine.

Every backend test for shared_view asserted what it SHOULD say, in isolation.
None fed the same fixtures through both shared_view.shared_rows and
projection.project_push to confirm they agree. This is the highest-risk
invariant in the branch — if the page ever disagrees with sync about which
rows are publishable, the user makes a decision from a screen that lies about
what will actually be pushed.
"""
import pytest
from fastapi.testclient import TestClient

import identity_service
import state
from main import app
from sheet_sync import contract, projection, shared_view

P1, P2 = "Valeria", "Christy"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def names(monkeypatch):
    monkeypatch.setattr(shared_view, "PERSON_1_NAME", P1)
    monkeypatch.setattr(shared_view, "PERSON_2_NAME", P2)


def txn(**over):
    base = {
        "date": "06/15/2026", "description": "Groceries", "amount": -112.25,
        "who": P1, "notes": "", "is_shared": True, "reviewed": True,
        "person_1_owes": 0.0, "person_2_owes": 56.13,
    }
    base.update(over)
    return base


class TestPublishabilityAgreesWithProjectPush:
    def test_every_blocked_reason_plus_a_publishable_row_agree_with_the_engine(
        self, client
    ):
        me = identity_service.ensure_identity()

        state.stored_transactions["good"] = txn()
        state.stored_transactions["unreviewed"] = txn(reviewed=False)
        state.stored_transactions["bad_date"] = txn(
            date="not-a-date", settles_in_period="2026-06"
        )
        state.stored_transactions["bad_who"] = txn(who="Mom")
        state.stored_transactions["bad_amount"] = txn(amount="not-a-number")
        state.stored_transactions["no_split"] = txn(
            person_1_owes=0.0, person_2_owes=0.0
        )

        body = client.get("/api/sync/shared-rows?period=2026-06").json()
        my_rows = [r for r in body["rows"] if r["owner"] == "me"]
        assert len(my_rows) == 6  # every fixture appears — none silently dropped

        desired, _unpublishable = projection.project_push(
            list(state.stored_transactions.items()), "2026-06",
            me["user_id"], P1, P2,
        )
        desired_txn_ids = {d.txn_id for d in desired}

        for row in my_rows:
            namespaced = contract.make_txn_id(me["user_id"], row["transaction_id"])
            if row["publishable"]:
                assert namespaced in desired_txn_ids, (
                    f"{row['transaction_id']} is publishable per shared_view "
                    f"but project_push withheld it"
                )
            else:
                assert namespaced not in desired_txn_ids, (
                    f"{row['transaction_id']} is NOT publishable per shared_view "
                    f"but project_push published it anyway"
                )
