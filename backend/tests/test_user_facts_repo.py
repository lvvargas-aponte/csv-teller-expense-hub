"""Integration tests for db.user_facts_repo against the real test DB."""
import pytest

from db import user_facts_repo


class TestCreateAndGet:
    def test_create_returns_full_row(self):
        row = user_facts_repo.create_fact(
            fact="User wants to retire at 45.",
            category="goal",
            tags=["retirement", "FI"],
        )
        assert row["id"] > 0
        assert row["fact"] == "User wants to retire at 45."
        assert row["category"] == "goal"
        assert row["tags"] == ["retirement", "FI"]
        assert row["status"] == "proposed"
        assert row["sensitive"] is False
        assert row["confidence"] == 0.5

    def test_get_round_trips(self):
        row = user_facts_repo.create_fact(fact="x", category="preference")
        fetched = user_facts_repo.get_fact(row["id"])
        assert fetched == row

    def test_get_missing_returns_none(self):
        assert user_facts_repo.get_fact(999_999) is None

    def test_invalid_category_rejected(self):
        with pytest.raises(ValueError):
            user_facts_repo.create_fact(fact="x", category="bogus")

    def test_invalid_status_rejected(self):
        with pytest.raises(ValueError):
            user_facts_repo.create_fact(fact="x", category="goal", status="bogus")


class TestList:
    def test_list_filters_by_status(self):
        user_facts_repo.create_fact(fact="a", category="goal", status="proposed")
        user_facts_repo.create_fact(fact="b", category="goal", status="confirmed")
        proposed = user_facts_repo.list_facts(status="proposed")
        confirmed = user_facts_repo.list_facts(status="confirmed")
        assert len(proposed) == 1 and proposed[0]["fact"] == "a"
        assert len(confirmed) == 1 and confirmed[0]["fact"] == "b"

    def test_list_filters_by_category(self):
        user_facts_repo.create_fact(fact="a", category="goal")
        user_facts_repo.create_fact(fact="b", category="preference")
        out = user_facts_repo.list_facts(category="goal")
        assert len(out) == 1 and out[0]["category"] == "goal"

    def test_list_orders_by_confidence_desc_then_updated_at(self):
        low = user_facts_repo.create_fact(fact="low", category="goal", confidence=0.2)
        high = user_facts_repo.create_fact(fact="high", category="goal", confidence=0.9)
        out = user_facts_repo.list_facts(category="goal")
        assert out[0]["id"] == high["id"]
        assert out[1]["id"] == low["id"]


class TestUpdate:
    def test_partial_update_only_changes_provided_fields(self):
        row = user_facts_repo.create_fact(fact="orig", category="goal", tags=["a"])
        updated = user_facts_repo.update_fact(row["id"], fact="new")
        assert updated["fact"] == "new"
        assert updated["tags"] == ["a"]
        assert updated["category"] == "goal"

    def test_update_tags_and_sensitive(self):
        row = user_facts_repo.create_fact(fact="x", category="goal")
        updated = user_facts_repo.update_fact(
            row["id"], tags=["debt", "urgent"], sensitive=True,
        )
        assert updated["tags"] == ["debt", "urgent"]
        assert updated["sensitive"] is True

    def test_update_missing_returns_none(self):
        assert user_facts_repo.update_fact(999_999, fact="x") is None


class TestStatusTransitions:
    def test_proposed_to_confirmed(self):
        row = user_facts_repo.create_fact(fact="x", category="goal")
        out = user_facts_repo.set_status(row["id"], "confirmed")
        assert out["status"] == "confirmed"

    def test_proposed_to_rejected(self):
        row = user_facts_repo.create_fact(fact="x", category="goal")
        out = user_facts_repo.set_status(row["id"], "rejected")
        assert out["status"] == "rejected"

    def test_invalid_status_rejected(self):
        row = user_facts_repo.create_fact(fact="x", category="goal")
        with pytest.raises(ValueError):
            user_facts_repo.set_status(row["id"], "bogus")


class TestDelete:
    def test_delete_returns_true_when_present(self):
        row = user_facts_repo.create_fact(fact="x", category="goal")
        assert user_facts_repo.delete_fact(row["id"]) is True
        assert user_facts_repo.get_fact(row["id"]) is None

    def test_delete_returns_false_when_absent(self):
        assert user_facts_repo.delete_fact(999_999) is False
