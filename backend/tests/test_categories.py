"""Categories as rows — rename, merge, archive, and the role sets.

The operations here are the ones that were impossible while a category was
just a string repeated across transactions. What they have to get right is
atomicity: a rename that lands on transactions but not budgets silently
drops a cap, and one that misses category_rules orphans a rule.
"""
import io

import categories_service
import state


def _upload(client):
    # "Bodega" is deliberately absent from category_normalizer.NORMALIZATION_MAP —
    # a mapped label (Supermarkets, Restaurants) is rewritten on ingest and
    # would never reach the table under its own name.
    csv = (
        "Trans. Date,Post Date,Description,Amount,Category\n"
        "01/15/2024,01/16/2024,TRADER JOE,-40.00,Groceries\n"
        "01/16/2024,01/17/2024,WHOLE FOODS,-22.00,Bodega\n"
        "01/17/2024,01/18/2024,SHELL,-30.00,Gas\n"
    )
    r = client.post(
        "/api/upload-csv",
        files={"file": ("d.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")},
    )
    return [t["id"] for t in r.json()["transactions"]]


def _named(client, name):
    return categories_service.find_by_name(name)


class TestSeed:
    def test_a_fresh_table_carries_the_default_vocabulary(self, client):
        names = [c["name"] for c in client.get("/api/categories").json()["rows"]]
        assert "Groceries" in names
        assert "Subscriptions" in names

    def test_the_seed_assigns_the_roles_analytics_used_to_hardcode(self, client):
        subs = _named(client, "Subscriptions")
        assert set(subs["roles"]) == {"always_recurring", "bill", "subscription"}
        # A label that only describes what something was for carries none.
        assert _named(client, "Groceries")["roles"] == []

    def test_counts_report_how_many_transactions_use_each(self, client):
        _upload(client)
        body = client.get("/api/categories").json()
        assert body["counts"]["Groceries"] == 1
        assert body["counts"]["Gas"] == 1


class TestRename:
    def test_renames_the_label_on_every_transaction(self, client):
        ids = _upload(client)
        groceries = _named(client, "Groceries")
        client.post(f"/api/categories/{groceries['id']}/rename", json={"name": "Food"})

        assert state.stored_transactions[ids[0]]["category"] == "Food"
        assert _named(client, "Food") is not None
        assert _named(client, "Groceries") is None

    def test_re_keys_a_budget_held_under_the_old_name(self, client):
        # Budgets are keyed *by* category, so a rename that misses them
        # silently drops the cap.
        client.put("/api/budgets/Groceries", json={"category": "Groceries", "monthly_limit": 400.0})
        groceries = _named(client, "Groceries")
        client.post(f"/api/categories/{groceries['id']}/rename", json={"name": "Food"})

        budgets = client.get("/api/budgets").json()
        names = [b["category"] for b in budgets]
        assert "Food" in names
        assert "Groceries" not in names

    def test_repoints_rules_that_targeted_the_old_name(self, client):
        client.put("/api/category-rules", json={
            "rules": [{"pattern": "TRADER JOE", "category": "Groceries"}],
        })
        groceries = _named(client, "Groceries")
        client.post(f"/api/categories/{groceries['id']}/rename", json={"name": "Food"})

        rules = client.get("/api/category-rules").json()
        assert rules[0]["category"] == "Food"

    def test_the_behaviour_follows_the_rename(self, client):
        # The whole reason roles moved onto the row: renaming "Subscriptions"
        # used to change recurring detection with nothing raising.
        subs = _named(client, "Subscriptions")
        client.post(f"/api/categories/{subs['id']}/rename", json={"name": "Streaming"})

        role = categories_service.names_with_role(categories_service.SUBSCRIPTION)
        assert "streaming" in role
        assert "subscriptions" not in role

    def test_changing_only_the_casing_keeps_one_category(self, client):
        groceries = _named(client, "Groceries")
        client.post(f"/api/categories/{groceries['id']}/rename", json={"name": "groceries"})
        assert _named(client, "GROCERIES")["name"] == "groceries"

    def test_renaming_onto_an_existing_name_merges(self, client):
        ids = _upload(client)
        supermarkets = _named(client, "Bodega")
        client.post(
            f"/api/categories/{supermarkets['id']}/rename", json={"name": "Groceries"}
        )
        assert _named(client, "Bodega") is None
        assert state.stored_transactions[ids[1]]["category"] == "Groceries"

    def test_a_blank_name_is_refused(self, client):
        groceries = _named(client, "Groceries")
        r = client.post(f"/api/categories/{groceries['id']}/rename", json={"name": "  "})
        assert r.status_code == 404
        assert _named(client, "Groceries") is not None


class TestMerge:
    def test_folds_one_label_into_another(self, client):
        # Replaces editing NORMALIZATION_MAP and redeploying.
        ids = _upload(client)
        src = _named(client, "Bodega")
        dst = _named(client, "Groceries")
        client.post(f"/api/categories/{src['id']}/merge", json={"into_id": dst["id"]})

        assert state.stored_transactions[ids[1]]["category"] == "Groceries"
        assert _named(client, "Bodega") is None

    def test_the_survivor_gains_both_role_sets(self, client):
        # A role is behaviour the user chose; dropping half of it on a merge
        # would change what counts as a bill.
        src = _named(client, "Subscriptions")
        dst = _named(client, "Entertainment")
        merged = client.post(
            f"/api/categories/{src['id']}/merge", json={"into_id": dst["id"]}
        ).json()
        assert set(merged["roles"]) >= {"always_recurring", "bill", "subscription"}

    def test_merging_a_category_into_itself_is_a_no_op(self, client):
        dst = _named(client, "Groceries")
        r = client.post(f"/api/categories/{dst['id']}/merge", json={"into_id": dst["id"]})
        assert r.status_code == 200
        assert _named(client, "Groceries") is not None

    def test_a_missing_category_is_404_not_a_partial_merge(self, client):
        dst = _named(client, "Groceries")
        r = client.post("/api/categories/99999/merge", json={"into_id": dst["id"]})
        assert r.status_code == 404


class TestArchive:
    def test_archiving_stops_it_being_offered_but_keeps_the_history(self, client):
        ids = _upload(client)
        gas = _named(client, "Gas")
        client.patch(f"/api/categories/{gas['id']}", json={"archived": True})

        assert "Gas" not in client.get("/api/categories").json()["categories"]
        assert state.stored_transactions[ids[2]]["category"] == "Gas"

    def test_archived_rows_are_visible_when_asked_for(self, client):
        gas = _named(client, "Gas")
        client.patch(f"/api/categories/{gas['id']}", json={"archived": True})
        body = client.get("/api/categories", params={"include_archived": True}).json()
        assert "Gas" in body["categories"]

    def test_the_suggester_stops_offering_an_archived_category(self, client):
        from categorizer import known_categories

        gas = _named(client, "Gas")
        client.patch(f"/api/categories/{gas['id']}", json={"archived": True})
        assert "Gas" not in known_categories()


class TestRoles:
    def test_roles_can_be_set_on_a_category_the_seed_left_bare(self, client):
        groceries = _named(client, "Groceries")
        client.patch(f"/api/categories/{groceries['id']}", json={"roles": ["non_spending"]})
        assert "groceries" in categories_service.names_with_role(
            categories_service.NON_SPENDING
        )

    def test_an_unknown_role_is_refused(self, client):
        groceries = _named(client, "Groceries")
        r = client.patch(f"/api/categories/{groceries['id']}", json={"roles": ["nonsense"]})
        assert r.status_code == 422

    def test_an_unreadable_table_degrades_to_the_old_hardcoded_sets(self, client, monkeypatch):
        # Analytics must not decide that nothing is a bill because the DB
        # hiccuped — that would reclassify every commitment at once.
        categories_service._invalidate()

        def _boom():
            raise RuntimeError("db gone")

        monkeypatch.setattr(categories_service.sync_engine, "connect", _boom)
        assert "utilities" in categories_service.names_with_role(
            categories_service.ALWAYS_RECURRING
        )
        # Undone here rather than at teardown: the autouse reset fixture runs
        # first and would hit the raising engine.
        monkeypatch.undo()

    def test_an_empty_table_also_degrades_rather_than_meaning_no_roles(self, client):
        from sqlalchemy import text

        categories_service._invalidate()
        with categories_service.sync_engine.begin() as conn:
            conn.execute(text("DELETE FROM categories"))
        assert "utilities" in categories_service.names_with_role(
            categories_service.ALWAYS_RECURRING
        )


class TestDelete:
    def test_clears_the_label_from_every_transaction(self, client):
        ids = _upload(client)
        gas = _named(client, "Gas")
        body = client.delete(f"/api/categories/id/{gas['id']}").json()

        assert body["cleared_txn_count"] == 1
        assert state.stored_transactions[ids[2]].get("category") is None
        assert state.stored_transactions[ids[2]].get("category_source") is None

    def test_deleting_by_name_still_works(self, client):
        _upload(client)
        assert client.delete("/api/categories/Gas").status_code == 200
        assert _named(client, "Gas") is None

    def test_a_budget_under_that_name_survives_and_is_reported(self, client):
        # A budget is a number the user set; the category row never owned it.
        client.put("/api/budgets/Gas", json={"category": "Gas", "monthly_limit": 120.0})
        gas = _named(client, "Gas")
        body = client.delete(f"/api/categories/id/{gas['id']}").json()

        assert body["budget_exists"] is True
        assert "Gas" in [b["category"] for b in client.get("/api/budgets").json()]

    def test_deleting_an_unknown_name_is_404(self, client):
        assert client.delete("/api/categories/NoSuchThing").status_code == 404
