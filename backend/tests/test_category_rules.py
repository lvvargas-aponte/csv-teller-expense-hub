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
            {"match": "TRADER JOE", "category": "Groceries"},
            {"match": "UBER",       "category": "Transport"},
            {"match": "SPOTIFY",    "category": "Subscriptions"},
        ]})
        assert r.status_code == 200
        body = r.json()
        assert [x["match"] for x in body] == ["TRADER JOE", "UBER", "SPOTIFY"]
        assert [x["position"] for x in body] == [0, 1, 2]

    def test_replace_is_a_full_overwrite(self, client):
        client.put("/api/category-rules", json={"rules": [
            {"match": "OLD", "category": "Shopping"},
        ]})
        body = client.put("/api/category-rules", json={"rules": [
            {"match": "NEW", "category": "Dining"},
        ]}).json()
        assert [x["match"] for x in body] == ["NEW"]

    def test_blank_rows_are_dropped(self, client):
        """"+ Add rule" seeds an empty row; an empty pattern would
        substring-match every transaction, so it must never persist."""
        body = client.put("/api/category-rules", json={"rules": [
            {"match": "UBER", "category": "Transport"},
            {"match": "",     "category": "Groceries"},
            {"match": "  ",   "category": "Groceries"},
            {"match": "LYFT", "category": ""},
        ]}).json()
        assert [x["match"] for x in body] == ["UBER"]

    def test_reordering_changes_which_rule_wins(self, client):
        client.put("/api/category-rules", json={"rules": [
            {"match": "AMAZON",       "category": "Shopping"},
            {"match": "AMAZON PRIME", "category": "Subscriptions"},
        ]})
        assert category_rules.match("AMAZON PRIME VIDEO") == "Shopping"

        client.put("/api/category-rules", json={"rules": [
            {"match": "AMAZON PRIME", "category": "Subscriptions"},
            {"match": "AMAZON",       "category": "Shopping"},
        ]})
        assert category_rules.match("AMAZON PRIME VIDEO") == "Subscriptions"


class TestMatching:
    def test_match_is_case_insensitive_substring(self, client):
        client.put("/api/category-rules", json={"rules": [
            {"match": "trader joe", "category": "Groceries"},
        ]})
        assert category_rules.match("TRADER JOE'S #481 SEATTLE") == "Groceries"

    def test_no_match_returns_none(self, client):
        client.put("/api/category-rules", json={"rules": [
            {"match": "UBER", "category": "Transport"},
        ]})
        assert category_rules.match("COSTCO WHOLESALE") is None

    def test_blank_description_never_matches(self, client):
        client.put("/api/category-rules", json={"rules": [
            {"match": "UBER", "category": "Transport"},
        ]})
        assert category_rules.match("") is None


class TestCategorizerIntegration:
    """The hybrid contract: rules first, Ollama only as the fallback."""

    @pytest.mark.asyncio
    async def test_rule_wins_without_calling_ollama(self, client, monkeypatch):
        client.put("/api/category-rules", json={"rules": [
            {"match": "SPOTIFY", "category": "Subscriptions"},
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
            {"match": "UBER", "category": "Transport"},
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
            {"match": "UBER", "category": "Transport"},
        ]})

        import categorizer

        async def _answers(*a, **kw):
            return {"ai_available": True, "text": "Groceries"}

        monkeypatch.setattr(categorizer, "ask_ollama", _answers)

        out = await categorizer.suggest_category("COSTCO WHOLESALE", 88.20)
        assert out["category"] == "Groceries"
        assert out["source"] == "ai"
        assert out["ai_available"] is True
