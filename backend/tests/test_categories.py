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


class TestGrouping:
    """Categories group one level deep so spending can be read as buckets."""

    def _group(self, client, child_name, parent_name):
        child = _named(client, child_name)
        parent = _named(client, parent_name)
        return client.post(
            f"/api/categories/{child['id']}/parent", json={"parent_id": parent["id"]}
        )

    def test_a_category_can_be_grouped_under_another(self, client):
        client.post("/api/categories", json={"name": "Food"})
        r = self._group(client, "Groceries", "Food")
        assert r.status_code == 200
        assert r.json()["parent_id"] == _named(client, "Food")["id"]

    def test_ungrouping_clears_the_parent(self, client):
        client.post("/api/categories", json={"name": "Food"})
        self._group(client, "Groceries", "Food")
        groceries = _named(client, "Groceries")
        r = client.post(f"/api/categories/{groceries['id']}/parent", json={"parent_id": None})
        assert r.json()["parent_id"] is None

    def test_nesting_deeper_than_one_level_is_refused(self, client):
        # Arbitrary depth means recursive rollups and a tree widget, for a
        # distinction nobody managing a household budget has asked for.
        client.post("/api/categories", json={"name": "Food"})
        self._group(client, "Groceries", "Food")
        food = _named(client, "Food")
        dining = _named(client, "Dining")
        r = client.post(f"/api/categories/{food['id']}/parent", json={"parent_id": dining["id"]})
        assert r.status_code == 422

    def test_a_parent_cannot_be_given_a_parent(self, client):
        client.post("/api/categories", json={"name": "Food"})
        client.post("/api/categories", json={"name": "Essentials"})
        self._group(client, "Groceries", "Food")
        r = self._group(client, "Food", "Essentials")
        assert r.status_code == 422

    def test_a_category_cannot_be_its_own_parent(self, client):
        groceries = _named(client, "Groceries")
        r = client.post(
            f"/api/categories/{groceries['id']}/parent",
            json={"parent_id": groceries["id"]},
        )
        assert r.status_code == 422

    def test_deleting_the_parent_leaves_the_children_alone(self, client):
        # ON DELETE SET NULL — losing "Food" must not delete Groceries.
        client.post("/api/categories", json={"name": "Food"})
        self._group(client, "Groceries", "Food")
        food = _named(client, "Food")
        client.delete(f"/api/categories/id/{food['id']}")

        groceries = _named(client, "Groceries")
        assert groceries is not None
        assert groceries["parent_id"] is None


class TestRollup:
    _csv = (
        "Trans. Date,Post Date,Description,Amount,Category\n"
        "01/15/2024,01/16/2024,TRADER JOE,-40.00,Groceries\n"
        "01/16/2024,01/17/2024,CHIPOTLE,-12.00,Dining\n"
        "01/17/2024,01/18/2024,SHELL,-30.00,Gas\n"
    )

    def _setup(self, client):
        client.post(
            "/api/upload-csv",
            files={"file": ("d.csv", io.BytesIO(self._csv.encode("utf-8")), "text/csv")},
        )
        client.post("/api/categories", json={"name": "Food"})
        food = _named(client, "Food")
        for name in ("Groceries", "Dining"):
            client.post(
                f"/api/categories/{_named(client, name)['id']}/parent",
                json={"parent_id": food["id"]},
            )
        return food

    def test_ungrouped_totals_are_unchanged_by_default(self, client):
        # Rolling up silently would make a Groceries cap look like it covered
        # Food, so the per-category answer stays the default.
        self._setup(client)
        from analytics import group_debit_spending

        month = group_debit_spending()["2024-01"]
        assert month["Groceries"] == 40.0
        assert month["Dining"] == 12.0
        assert "Food" not in month

    def test_rolled_up_totals_bucket_children_under_the_parent(self, client):
        self._setup(client)
        from analytics import group_debit_spending

        month = group_debit_spending(rolled_up=True)["2024-01"]
        assert month["Food"] == 52.0
        assert "Groceries" not in month
        # An ungrouped category still reports under its own name.
        assert month["Gas"] == 30.0

    def test_the_dashboard_reports_which_view_it_returned(self, client):
        self._setup(client)
        assert client.get("/api/dashboard").json()["rolled_up"] is False
        body = client.get("/api/dashboard", params={"rolled_up": True}).json()
        assert body["rolled_up"] is True
        assert body["spending_by_month"]["2024-01"]["Food"] == 52.0

    def test_a_budget_on_a_parent_counts_what_its_children_spent(self, client):
        # Matching on the name alone would report the parent at zero forever.
        self._setup(client)
        client.put("/api/budgets/Food", json={"category": "Food", "monthly_limit": 100.0})

        from analytics import compute_budget_statuses
        from datetime import date

        statuses = compute_budget_statuses(today=date(2024, 1, 20))
        food = next(b for b in statuses if b["category"] == "Food")
        assert food["current_month_spent"] == 52.0

    def test_a_budget_on_a_child_still_counts_only_that_child(self, client):
        self._setup(client)
        client.put(
            "/api/budgets/Groceries",
            json={"category": "Groceries", "monthly_limit": 100.0},
        )

        from analytics import compute_budget_statuses
        from datetime import date

        statuses = compute_budget_statuses(today=date(2024, 1, 20))
        groceries = next(b for b in statuses if b["category"] == "Groceries")
        assert groceries["current_month_spent"] == 40.0

    def test_renaming_a_parent_keeps_the_grouping(self, client):
        food = self._setup(client)
        client.post(f"/api/categories/{food['id']}/rename", json={"name": "Eating"})

        from analytics import group_debit_spending

        assert group_debit_spending(rolled_up=True)["2024-01"]["Eating"] == 52.0

    def test_the_advisor_snapshot_omits_the_rolled_view_until_grouping_exists(self, client):
        # An empty dict there would read as "nothing was spent" rather than
        # "no grouping is configured".
        client.post(
            "/api/upload-csv",
            files={"file": ("d.csv", io.BytesIO(self._csv.encode("utf-8")), "text/csv")},
        )
        from analytics import build_financial_snapshot

        assert "spending_by_month_rolled_up" not in build_financial_snapshot()

    def test_the_advisor_snapshot_carries_both_levels_once_grouped(self, client):
        self._setup(client)
        from analytics import build_financial_snapshot

        snap = build_financial_snapshot()
        assert snap["spending_by_month"]["2024-01"]["Groceries"] == 40.0
        assert snap["spending_by_month_rolled_up"]["2024-01"]["Food"] == 52.0
