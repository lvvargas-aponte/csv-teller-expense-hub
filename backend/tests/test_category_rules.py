"""Category rules — user-authored merchant matching ahead of Ollama.

Pins the two things that make the hybrid work: a rule beats the model,
and a rule still answers when the model is unreachable.
"""
import pytest

import category_rules


class TestRulesCrud:
    def test_empty_by_default(self, client):
        assert client.get("/api/category-rules").json() == []

    def test_replace_assigns_positions_in_list_order(self, client):
        r = client.put("/api/category-rules", json={"rules": [
            {"pattern": "TRADER JOE", "category": "Groceries"},
            {"pattern": "UBER",       "category": "Transport"},
            {"pattern": "SPOTIFY",    "category": "Subscriptions"},
        ]})
        assert r.status_code == 200
        body = r.json()
        assert [x["pattern"] for x in body] == ["TRADER JOE", "UBER", "SPOTIFY"]
        assert [x["position"] for x in body] == [0, 1, 2]

    def test_replace_is_a_full_overwrite(self, client):
        client.put("/api/category-rules", json={"rules": [
            {"pattern": "OLD", "category": "Shopping"},
        ]})
        body = client.put("/api/category-rules", json={"rules": [
            {"pattern": "NEW", "category": "Dining"},
        ]}).json()
        assert [x["pattern"] for x in body] == ["NEW"]

    def test_blank_rows_are_dropped(self, client):
        """"+ Add rule" seeds an empty row; an empty pattern would
        substring-match every transaction, so it must never persist."""
        body = client.put("/api/category-rules", json={"rules": [
            {"pattern": "UBER", "category": "Transport"},
            {"pattern": "",     "category": "Groceries"},
            {"pattern": "  ",   "category": "Groceries"},
            {"pattern": "LYFT", "category": ""},
        ]}).json()
        assert [x["pattern"] for x in body] == ["UBER"]

    def test_reordering_changes_which_rule_wins(self, client):
        client.put("/api/category-rules", json={"rules": [
            {"pattern": "AMAZON",       "category": "Shopping"},
            {"pattern": "AMAZON PRIME", "category": "Subscriptions"},
        ]})
        assert category_rules.match("AMAZON PRIME VIDEO") == "Shopping"

        client.put("/api/category-rules", json={"rules": [
            {"pattern": "AMAZON PRIME", "category": "Subscriptions"},
            {"pattern": "AMAZON",       "category": "Shopping"},
        ]})
        assert category_rules.match("AMAZON PRIME VIDEO") == "Subscriptions"


class TestMatching:
    def test_match_is_case_insensitive_substring(self, client):
        client.put("/api/category-rules", json={"rules": [
            {"pattern": "trader joe", "category": "Groceries"},
        ]})
        assert category_rules.match("TRADER JOE'S #481 SEATTLE") == "Groceries"

    def test_no_match_returns_none(self, client):
        client.put("/api/category-rules", json={"rules": [
            {"pattern": "UBER", "category": "Transport"},
        ]})
        assert category_rules.match("COSTCO WHOLESALE") is None

    def test_blank_description_never_matches(self, client):
        client.put("/api/category-rules", json={"rules": [
            {"pattern": "UBER", "category": "Transport"},
        ]})
        assert category_rules.match("") is None


class TestCategorizerIntegration:
    """The hybrid contract: rules first, Ollama only as the fallback."""

    @pytest.mark.asyncio
    async def test_rule_wins_without_calling_ollama(self, client, monkeypatch):
        client.put("/api/category-rules", json={"rules": [
            {"pattern": "SPOTIFY", "category": "Subscriptions"},
        ]})

        import categorizer

        async def _boom(*a, **kw):
            raise AssertionError("Ollama must not be consulted on a rule hit")

        monkeypatch.setattr(categorizer, "ask_ollama", _boom)

        out = await categorizer.suggest_category("SPOTIFY USA", 11.99)
        assert out["category"] == "Subscriptions"
        assert out["source"] == "rule"
        # Never asked. ``source == "rule"`` is what says so — the flag keeps
        # its repo-wide meaning ("Ollama answered") and is False here.
        assert out["ai_available"] is False

    @pytest.mark.asyncio
    async def test_rule_still_answers_with_ollama_down(self, client, monkeypatch):
        client.put("/api/category-rules", json={"rules": [
            {"pattern": "UBER", "category": "Transport"},
        ]})

        import categorizer

        async def _down(*a, **kw):
            return {"ai_available": False, "text": None}

        monkeypatch.setattr(categorizer, "ask_ollama", _down)

        out = await categorizer.suggest_category("UBER TRIP 4AM", 24.10)
        assert out["category"] == "Transport"
        assert out["source"] == "rule"

    @pytest.mark.asyncio
    async def test_falls_through_to_ollama_when_no_rule_matches(self, client, monkeypatch):
        client.put("/api/category-rules", json={"rules": [
            {"pattern": "UBER", "category": "Transport"},
        ]})

        import categorizer

        async def _answers(*a, **kw):
            return {"ai_available": True, "text": "Groceries"}

        monkeypatch.setattr(categorizer, "ask_ollama", _answers)

        out = await categorizer.suggest_category("COSTCO WHOLESALE", 88.20)
        assert out["category"] == "Groceries"
        assert out["source"] == "ai"
        assert out["ai_available"] is True


class TestMerchantRules:
    """Rules keyed on the normalized merchant key rather than a substring."""

    def _rule(self, client, pattern="chipotle", category="Dining", **extra):
        return client.post("/api/category-rules", json={
            "pattern": pattern, "category": category, "kind": "merchant", **extra,
        })

    def test_matches_across_the_noise_banks_append(self, client):
        # The whole point: one merchant, many descriptions. Store numbers,
        # processor prefixes and the trailing state code all fall out.
        self._rule(client)
        assert category_rules.match("CHIPOTLE 4471") == "Dining"
        assert category_rules.match("SQ *CHIPOTLE 8812") == "Dining"
        assert category_rules.match("chipotle WA") == "Dining"

    def test_a_city_in_the_description_forks_the_key(self, client):
        # Documented limitation of merchant_key.normalize: it strips the
        # 2-letter state code but keeps the city, so the same merchant in two
        # cities is two keys. merchant_aliases is the remedy, not a wider
        # regex — fuzzy-merging names would fold unrelated merchants.
        self._rule(client)
        assert category_rules.match("CHIPOTLE 4471 SEATTLE WA") is None

    def test_does_not_match_a_different_merchant(self, client):
        self._rule(client)
        assert category_rules.match("CHIPOTLE MEXICAN GRILL SUPPLY CO") != "Dining"

    def test_beats_a_substring_rule_regardless_of_position(self, client):
        # A merchant key is an exact statement; a substring is a guess about
        # which fragment is stable, so precision wins over authoring order.
        client.put("/api/category-rules", json={
            "rules": [{"pattern": "CHIPOTLE", "category": "Shopping"}],
        })
        self._rule(client, category="Dining")
        assert category_rules.match("CHIPOTLE 4471") == "Dining"

    def test_restating_a_merchant_updates_rather_than_duplicates(self, client):
        self._rule(client, category="Dining")
        self._rule(client, category="Fast Food")
        merchant_rules = [
            r for r in client.get("/api/category-rules").json()
            if r["kind"] == "merchant"
        ]
        assert len(merchant_rules) == 1
        assert merchant_rules[0]["category"] == "Fast Food"

    def test_a_disabled_rule_stops_matching_but_survives(self, client):
        rule = self._rule(client).json()["rule"]
        client.patch(f"/api/category-rules/{rule['id']}", json={"enabled": False})
        assert category_rules.match("CHIPOTLE 4471") is None
        assert any(
            r["id"] == rule["id"] for r in client.get("/api/category-rules").json()
        )

    def test_deleting_one_returns_404_the_second_time(self, client):
        rule = self._rule(client).json()["rule"]
        assert client.delete(f"/api/category-rules/{rule['id']}").status_code == 200
        assert client.delete(f"/api/category-rules/{rule['id']}").status_code == 404

    def test_replacing_the_substring_list_leaves_merchant_rules_alone(self, client):
        # The settings form does not show merchant rules, so its whole-list
        # save must not delete them.
        self._rule(client)
        client.put("/api/category-rules", json={
            "rules": [{"pattern": "UBER", "category": "Transport"}],
        })
        kinds = [r["kind"] for r in client.get("/api/category-rules").json()]
        assert kinds.count("merchant") == 1
        assert kinds.count("contains") == 1

    def test_blank_pattern_is_rejected(self, client):
        assert self._rule(client, pattern="  ").status_code == 422


class TestForMerchant:
    def test_reports_the_key_and_that_no_rule_exists_yet(self, client):
        body = client.get(
            "/api/category-rules/for-merchant",
            params={"description": "SQ *CHIPOTLE 4471 SEATTLE WA"},
        ).json()
        assert body["merchant_key"] == "chipotle seattle"
        assert body["rule"] is None

    def test_reports_the_rule_once_there_is_one(self, client):
        client.post("/api/category-rules", json={
            "pattern": "chipotle", "category": "Dining", "kind": "merchant",
        })
        body = client.get(
            "/api/category-rules/for-merchant",
            params={"description": "CHIPOTLE 8812"},
        ).json()
        assert body["rule"]["category"] == "Dining"


class TestPreviewAndApply:
    _csv = (
        "Trans. Date,Post Date,Description,Amount,Category\n"
        "01/15/2024,01/16/2024,CHIPOTLE 4471,-12.50,\n"
        "01/16/2024,01/17/2024,CHIPOTLE 8812,-9.25,\n"
        "01/17/2024,01/18/2024,UBER TRIP,-24.10,\n"
    )

    def _upload(self, client):
        import io
        r = client.post(
            "/api/upload-csv",
            files={"file": ("d.csv", io.BytesIO(self._csv.encode("utf-8")), "text/csv")},
        )
        return [t["id"] for t in r.json()["transactions"]]

    def test_preview_counts_without_writing(self, client):
        ids = self._upload(client)
        body = client.post("/api/category-rules/preview", json={
            "pattern": "chipotle", "category": "Dining", "kind": "merchant",
        }).json()
        assert body["matched"] == 2
        assert body["claimable"] == 2

        import state
        assert state.stored_transactions[ids[0]].get("category") is None

    def test_apply_to_existing_sweeps_matching_rows(self, client):
        ids = self._upload(client)
        client.post("/api/category-rules", json={
            "pattern": "chipotle", "category": "Dining", "kind": "merchant",
            "apply_to_existing": True,
        })

        import state
        assert state.stored_transactions[ids[0]]["category"] == "Dining"
        assert state.stored_transactions[ids[1]]["category"] == "Dining"
        assert state.stored_transactions[ids[0]]["category_source"] == "rule"
        # The unrelated row is untouched.
        assert state.stored_transactions[ids[2]].get("category") is None

    def test_without_the_flag_existing_rows_are_left_alone(self, client):
        ids = self._upload(client)
        client.post("/api/category-rules", json={
            "pattern": "chipotle", "category": "Dining", "kind": "merchant",
        })
        import state
        assert state.stored_transactions[ids[0]].get("category") is None

    def test_a_sweep_never_overwrites_what_you_typed(self, client):
        # The reason provenance exists: retro-apply has to be safe to offer.
        ids = self._upload(client)
        client.put("/api/transactions/categories", json={
            "items": [{"transaction_id": ids[0], "category": "Takeout"}],
        })
        body = client.post("/api/category-rules", json={
            "pattern": "chipotle", "category": "Dining", "kind": "merchant",
            "apply_to_existing": True,
        }).json()

        import state
        assert state.stored_transactions[ids[0]]["category"] == "Takeout"
        assert state.stored_transactions[ids[1]]["category"] == "Dining"
        assert body["applied"]["updated"] == 1
        assert body["applied"]["protected"] == 1

    def test_applying_an_existing_rule_by_id(self, client):
        ids = self._upload(client)
        rule = client.post("/api/category-rules", json={
            "pattern": "chipotle", "category": "Dining", "kind": "merchant",
        }).json()["rule"]

        body = client.post(f"/api/category-rules/{rule['id']}/apply").json()
        assert body["updated"] == 2

        import state
        assert state.stored_transactions[ids[0]]["category"] == "Dining"
