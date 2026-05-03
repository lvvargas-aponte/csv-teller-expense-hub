"""Unit + endpoint tests for the LLM-backed category suggester.

Ollama is mocked everywhere so these tests run offline. The point isn't to
validate the LLM's output quality (that's a manual / eval concern), but
to pin down the contract:

* ``known_categories()`` merges budgets over defaults without dupes.
* The strict prompt only accepts responses whose text matches a known
  category — everything else becomes ``None``.
* The endpoint never writes to the transaction.
"""
import io
from unittest.mock import AsyncMock, patch

import pytest

import state
from categorizer import (
    DEFAULT_CATEGORIES,
    _build_prompt,
    _parse_response,
    known_categories,
    suggest_category,
)


class TestKnownCategories:
    def test_defaults_only_when_no_budgets(self, client):
        assert known_categories() == DEFAULT_CATEGORIES

    def test_budgets_take_precedence(self, client):
        state.budgets["Groceries"] = {"category": "Groceries", "monthly_limit": 400}
        state.budgets["Coffee"]    = {"category": "Coffee",    "monthly_limit": 50}

        result = known_categories()
        # Budget casing preserved, not duplicated
        assert "Groceries" in result
        assert "Coffee" in result
        lowered = [x.lower() for x in result]
        assert lowered.count("groceries") == 1
        # Defaults still present
        assert "Dining" in result
        assert "Other" in result

    def test_empty_budget_keys_skipped(self, client):
        state.budgets[""]    = {"category": "", "monthly_limit": 0}
        state.budgets["  "]  = {"category": "  ", "monthly_limit": 0}
        result = known_categories()
        assert "" not in result
        assert all(r.strip() for r in result)


class TestParseResponse:
    _known = ["Groceries", "Dining", "Gas"]

    def test_exact_match(self):
        assert _parse_response("Groceries", self._known) == "Groceries"

    def test_case_insensitive_returns_canonical(self):
        assert _parse_response("groceries", self._known) == "Groceries"
        assert _parse_response("DINING",     self._known) == "Dining"

    def test_trailing_punctuation_tolerated(self):
        assert _parse_response("Groceries.",  self._known) == "Groceries"
        assert _parse_response("  Gas  ",     self._known) == "Gas"

    def test_none_response_yields_none(self):
        assert _parse_response("NONE",  self._known) is None
        assert _parse_response("none",  self._known) is None

    def test_unknown_category_yields_none(self):
        assert _parse_response("Crypto",             self._known) is None
        assert _parse_response("Some rambling text", self._known) is None
        assert _parse_response("",                   self._known) is None
        assert _parse_response(None,                 self._known) is None


class TestBuildPrompt:
    def test_prompt_includes_merchant_amount_and_list(self):
        prompt = _build_prompt("WHOLE FOODS", -52.30, ["Groceries", "Dining"])
        assert "WHOLE FOODS" in prompt
        assert "-$52.30" in prompt
        assert "Groceries, Dining" in prompt
        # Strictness signal present
        assert "ONLY" in prompt


class TestSuggestCategory:
    @pytest.mark.asyncio
    async def test_returns_canonical_match(self, client):
        mock_ask = AsyncMock(return_value={
            "ai_available": True, "text": "groceries", "raw": None,
        })
        with patch("categorizer.ask_ollama", mock_ask):
            result = await suggest_category("WHOLE FOODS", -52.30)
        assert result["ai_available"] is True
        assert result["category"] == "Groceries"
        assert "Groceries" in result["candidates"]

    @pytest.mark.asyncio
    async def test_none_when_llm_returns_unknown(self, client):
        mock_ask = AsyncMock(return_value={
            "ai_available": True, "text": "Cryptocurrency", "raw": None,
        })
        with patch("categorizer.ask_ollama", mock_ask):
            result = await suggest_category("COINBASE", -100.00)
        assert result["ai_available"] is True
        assert result["category"] is None

    @pytest.mark.asyncio
    async def test_ollama_down_degrades_gracefully(self, client):
        mock_ask = AsyncMock(return_value={
            "ai_available": False, "text": None, "raw": None,
        })
        with patch("categorizer.ask_ollama", mock_ask):
            result = await suggest_category("ANYTHING", -1.00)
        assert result["ai_available"] is False
        assert result["category"] is None
        # Candidates still populated so the UI can offer manual entry
        assert len(result["candidates"]) > 0


class TestBulkSuggestEndpoint:
    _csv = (
        "Trans. Date,Post Date,Description,Amount,Category\n"
        "01/15/2024,01/16/2024,WHOLE FOODS,-52.30,\n"
        "01/16/2024,01/17/2024,SHELL GAS,-40.00,\n"
        "01/17/2024,01/18/2024,NETFLIX,-15.99,\n"
    )

    def _upload_three(self, client):
        r = client.post(
            "/api/upload-csv",
            files={"file": ("disco.csv", io.BytesIO(self._csv.encode("utf-8")), "text/csv")},
        )
        return [t["id"] for t in r.json()["transactions"]]

    def test_returns_suggestions_without_mutating(self, client):
        ids = self._upload_three(client)
        pre = {tid: dict(state.stored_transactions[tid]) for tid in ids}

        mock_ask = AsyncMock(side_effect=[
            {"ai_available": True, "text": "Groceries",     "raw": None},
            {"ai_available": True, "text": "Gas",           "raw": None},
            {"ai_available": True, "text": "Subscriptions", "raw": None},
        ])
        with patch("categorizer.ask_ollama", mock_ask):
            r = client.post("/api/transactions/suggest-categories/bulk",
                            json={"transaction_ids": ids})

        assert r.status_code == 200
        body = r.json()
        assert body["ai_available"] is True
        assert len(body["results"]) == 3
        cats = [row["suggested_category"] for row in body["results"]]
        assert "Groceries" in cats and "Gas" in cats and "Subscriptions" in cats
        assert body["skipped_ids"] == []
        assert body["not_found"] == []
        # No mutation
        for tid in ids:
            assert dict(state.stored_transactions[tid]) == pre[tid]

    def test_skips_already_categorized(self, client):
        ids = self._upload_three(client)
        # Pre-categorize one
        t = state.stored_transactions[ids[0]]
        t["category"] = "Groceries"
        state.stored_transactions[ids[0]] = t

        mock_ask = AsyncMock(return_value={
            "ai_available": True, "text": "Gas", "raw": None,
        })
        with patch("categorizer.ask_ollama", mock_ask):
            r = client.post("/api/transactions/suggest-categories/bulk",
                            json={"transaction_ids": ids})

        body = r.json()
        assert ids[0] in body["skipped_ids"]
        assert len(body["results"]) == 2
        assert all(row["id"] != ids[0] for row in body["results"])

    def test_unknown_ids_in_not_found(self, client):
        ids = self._upload_three(client)
        mock_ask = AsyncMock(return_value={
            "ai_available": True, "text": "Groceries", "raw": None,
        })
        with patch("categorizer.ask_ollama", mock_ask):
            r = client.post("/api/transactions/suggest-categories/bulk",
                            json={"transaction_ids": ids + ["bogus-id"]})

        assert r.status_code == 200
        assert r.json()["not_found"] == ["bogus-id"]

    def test_ollama_unavailable_returns_flag_and_results(self, client):
        ids = self._upload_three(client)
        mock_ask = AsyncMock(return_value={
            "ai_available": False, "text": None, "raw": None,
        })
        with patch("categorizer.ask_ollama", mock_ask):
            r = client.post("/api/transactions/suggest-categories/bulk",
                            json={"transaction_ids": ids})

        assert r.status_code == 200
        body = r.json()
        assert body["ai_available"] is False
        assert len(body["results"]) == 3
        assert all(row["suggested_category"] is None for row in body["results"])
        assert len(body["candidates"]) > 0


class TestApplyCategoriesEndpoint:
    _csv = (
        "Trans. Date,Post Date,Description,Amount,Category\n"
        "01/15/2024,01/16/2024,WHOLE FOODS,-52.30,\n"
        "01/16/2024,01/17/2024,SHELL GAS,-40.00,\n"
    )

    def _upload_two(self, client):
        r = client.post(
            "/api/upload-csv",
            files={"file": ("disco.csv", io.BytesIO(self._csv.encode("utf-8")), "text/csv")},
        )
        return [t["id"] for t in r.json()["transactions"]]

    def test_applies_assignments_and_marks_reviewed(self, client):
        ids = self._upload_two(client)
        r = client.put("/api/transactions/categories", json={
            "items": [
                {"transaction_id": ids[0], "category": "Groceries"},
                {"transaction_id": ids[1], "category": "Gas"},
            ],
        })
        assert r.status_code == 200
        assert r.json()["updated"] == 2
        assert state.stored_transactions[ids[0]]["category"] == "Groceries"
        assert state.stored_transactions[ids[1]]["category"] == "Gas"
        assert state.stored_transactions[ids[0]]["reviewed"] is True
        assert state.stored_transactions[ids[1]]["reviewed"] is True

    def test_empty_string_clears_category(self, client):
        ids = self._upload_two(client)
        t = state.stored_transactions[ids[0]]
        t["category"] = "Groceries"
        state.stored_transactions[ids[0]] = t

        r = client.put("/api/transactions/categories", json={
            "items": [{"transaction_id": ids[0], "category": ""}],
        })
        assert r.status_code == 200
        assert state.stored_transactions[ids[0]]["category"] == ""

    def test_unknown_ids_in_not_found_no_500(self, client):
        ids = self._upload_two(client)
        r = client.put("/api/transactions/categories", json={
            "items": [
                {"transaction_id": ids[0], "category": "Groceries"},
                {"transaction_id": "bogus", "category": "Gas"},
            ],
        })
        assert r.status_code == 200
        body = r.json()
        assert body["updated"] == 1
        assert body["not_found"] == ["bogus"]
