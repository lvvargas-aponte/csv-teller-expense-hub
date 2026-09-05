"""merchant_key — the shared merchant-key normalizer.

The ``normalize`` pipeline is exercised in depth by ``test_analytics`` (which
imports it under the name analytics has always used). These cover the alias
fold, which is what the category rules will key on.
"""
import merchant_key


class TestCanonical:
    def test_folds_an_alias_onto_its_canonical_key(self):
        alias_map = {"twitter": "x corp"}
        assert merchant_key.canonical("TWITTER #4471", alias_map) == "x corp"

    def test_passes_through_a_merchant_with_no_alias(self):
        assert merchant_key.canonical("SQ *STARBUCKS 123", {}) == "starbucks"

    def test_empty_description_yields_empty_key_without_reading_aliases(self):
        # alias_map=None would hit the DB; an empty description must short-circuit.
        assert merchant_key.canonical("") == ""

    def test_two_charges_from_one_merchant_share_a_key(self):
        a = merchant_key.canonical("SQ *AZZURRA HEALTH CARE Doral FL", {})
        b = merchant_key.canonical("SQ *AZZURRA HEALTH CARE Doral", {})
        assert a == b


class TestAliases:
    def test_degrades_to_empty_when_the_table_is_unreachable(self, monkeypatch):
        # An unmerged merchant is a worse answer than no answer, but it is
        # still an answer — reading aliases must never raise.
        import sys
        monkeypatch.setitem(sys.modules, "db.merchant_aliases_repo", None)
        assert merchant_key.aliases() == {}
