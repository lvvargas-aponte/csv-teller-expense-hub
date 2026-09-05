"""categorization_service — who may set a category, and who wins.

The precedence is manual > rule > bank > ai. The cases that matter are the
downgrades: a re-sync must not undo a typed label, and the suggester must
not overwrite either.
"""
import pytest

import categorization_service as cs


def txn(category=None, source=None, **extra):
    t = {"description": "CHIPOTLE 4471", "amount": 12.5, **extra}
    if category is not None:
        t["category"] = category
    if source is not None:
        t["category_source"] = source
    return t


class TestCurrentSource:
    def test_uncategorized_row_has_no_owner(self):
        assert cs.current_source(txn()) is None
        assert cs.current_source(txn(category="")) is None
        assert cs.current_source(txn(category="   ")) is None

    def test_categorized_row_without_a_source_reads_as_bank(self):
        # Pre-provenance data: it came from a feed or a CSV.
        assert cs.current_source(txn(category="Dining")) == cs.BANK

    def test_unrecognized_source_reads_as_bank_rather_than_raising(self):
        assert cs.current_source(txn(category="Dining", source="nonsense")) == cs.BANK

    def test_source_is_case_insensitive(self):
        assert cs.current_source(txn(category="Dining", source="MANUAL")) == cs.MANUAL


class TestPrecedence:
    def test_anyone_may_claim_an_uncategorized_row(self):
        for source in cs.SOURCES:
            assert cs.can_assign(txn(), source) is True

    @pytest.mark.parametrize("holder,claimant,allowed", [
        (cs.MANUAL, cs.AI,     False),
        (cs.MANUAL, cs.BANK,   False),
        (cs.MANUAL, cs.RULE,   False),
        (cs.MANUAL, cs.MANUAL, True),
        (cs.RULE,   cs.AI,     False),
        (cs.RULE,   cs.BANK,   False),
        (cs.RULE,   cs.RULE,   True),
        (cs.RULE,   cs.MANUAL, True),
        (cs.BANK,   cs.AI,     False),
        (cs.BANK,   cs.BANK,   True),
        (cs.BANK,   cs.RULE,   True),
        (cs.AI,     cs.AI,     True),
        (cs.AI,     cs.BANK,   True),
    ])
    def test_a_claimant_needs_to_match_or_outrank_the_holder(
        self, holder, claimant, allowed
    ):
        t = txn(category="Dining", source=holder)
        assert cs.can_assign(t, claimant) is allowed


class TestApply:
    def test_setting_a_category_records_its_source(self):
        t = txn()
        assert cs.apply(t, "Dining", cs.RULE) is True
        assert t["category"] == "Dining"
        assert t["category_source"] == cs.RULE

    def test_a_resync_cannot_overwrite_a_typed_label(self):
        # The bug this phase exists to fix: SimpleFIN refreshed `category` on
        # every seen transaction, so the feed's label won every sync.
        t = txn(category="Dining", source=cs.MANUAL)
        assert cs.apply(t, "Restaurants", cs.BANK) is False
        assert t["category"] == "Dining"
        assert t["category_source"] == cs.MANUAL

    def test_a_resync_still_refreshes_its_own_label(self):
        t = txn(category="Dining", source=cs.BANK)
        assert cs.apply(t, "Restaurants", cs.BANK) is True
        assert t["category"] == "Restaurants"

    def test_the_suggester_cannot_overwrite_a_rule(self):
        t = txn(category="Dining", source=cs.RULE)
        assert cs.apply(t, "Shopping", cs.AI) is False
        assert t["category"] == "Dining"

    def test_a_rule_may_replace_a_bank_label(self):
        t = txn(category="Merchandise", source=cs.BANK)
        assert cs.apply(t, "Shopping", cs.RULE) is True
        assert t["category_source"] == cs.RULE

    def test_category_is_stripped(self):
        t = txn()
        cs.apply(t, "  Dining  ", cs.MANUAL)
        assert t["category"] == "Dining"

    def test_clearing_drops_the_source_too(self):
        t = txn(category="Dining", source=cs.MANUAL)
        assert cs.apply(t, "", cs.MANUAL) is True
        assert t["category"] is None
        assert t["category_source"] is None

    def test_a_blank_string_clears_the_same_way_as_none(self):
        t = txn(category="Dining", source=cs.MANUAL)
        cs.apply(t, None, cs.MANUAL)
        assert t["category"] is None

    def test_a_lower_source_cannot_clear_a_higher_one(self):
        t = txn(category="Dining", source=cs.MANUAL)
        assert cs.apply(t, None, cs.AI) is False
        assert t["category"] == "Dining"

    def test_an_unknown_source_is_a_programming_error(self):
        with pytest.raises(ValueError, match="unknown category source"):
            cs.apply(txn(), "Dining", "guess")


class TestStampIngest:
    def test_a_fresh_row_with_a_category_is_bank_sourced(self):
        t = cs.stamp_ingest({"category": "Groceries"})
        assert t["category_source"] == cs.BANK

    def test_a_fresh_row_without_one_gets_no_source(self):
        assert cs.stamp_ingest({"category": None})["category_source"] is None
        assert cs.stamp_ingest({})["category_source"] is None
