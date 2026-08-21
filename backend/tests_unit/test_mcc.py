"""Unit tests for the MCC → category mapping.

The mapping table itself isn't worth asserting code-by-code — it's data, and
a test that restates it just breaks twice when it changes. What's pinned
here is the behaviour around it: the vocabulary stays inside the categories
the rest of the app knows, junk input never produces a confident answer, and
the codes actually present in the connected accounts resolve the way the
account holder would expect.
"""
import pytest

from categorizer import DEFAULT_CATEGORIES
from mcc import _CODES_BY_CATEGORY, _RANGE_CATEGORIES, category_for_mcc


class TestVocabulary:
    """Everything emitted has to be a category the app already understands."""

    def test_every_target_is_a_known_default(self):
        emitted = set(_CODES_BY_CATEGORY) | {cat for _, _, cat in _RANGE_CATEGORIES}
        assert emitted <= set(DEFAULT_CATEGORIES)

    def test_entity_buckets_are_never_auto_assigned(self):
        # Which LLC or rental a charge belongs to is a fact about intent, not
        # about the merchant — no code can imply it.
        emitted = set(_CODES_BY_CATEGORY) | {cat for _, _, cat in _RANGE_CATEGORIES}
        assert not any(c.startswith("Rental:") for c in emitted)
        assert "Tomatillo LLC" not in emitted

    def test_no_code_maps_to_two_categories(self):
        # _build_lookup raises on import if this is violated; assert the
        # invariant directly so the reason survives a refactor of the loader.
        seen = set()
        for codes in _CODES_BY_CATEGORY.values():
            for code in codes:
                assert code not in seen, f"MCC {code} listed twice"
                seen.add(code)

    def test_all_codes_are_four_digit_strings(self):
        for codes in _CODES_BY_CATEGORY.values():
            for code in codes:
                assert isinstance(code, str) and len(code) == 4 and code.isdigit()


class TestUnknownInput:
    """Anything uncertain must return None, never a fallback label.

    None means "still needs a category" to the ingest path and the bulk
    suggester; a label — even "Other" — means "decided", which would quietly
    remove the transaction from everything that surfaces uncategorized rows.
    """

    @pytest.mark.parametrize("raw", [None, "", "   ", "abcd", "55a1", "12.5", "-5411"])
    def test_junk_returns_none(self, raw):
        assert category_for_mcc(raw) is None

    def test_all_zero_placeholder_returns_none(self):
        # Every card-payment/autopay row in the live data arrives as "0000".
        assert category_for_mcc("0000") is None

    def test_too_long_returns_none(self):
        assert category_for_mcc("54110") is None

    def test_unmapped_but_valid_code_returns_none(self):
        # 1711 (heating/plumbing contractors) is real and appears in the live
        # data, but has no honest home in DEFAULT_CATEGORIES.
        assert category_for_mcc("1711") is None

    def test_tax_payments_stay_unmapped(self):
        assert category_for_mcc("9311") is None


class TestNormalization:
    def test_short_codes_are_left_padded(self):
        # Issuers inconsistently drop the leading zero.
        assert category_for_mcc("711") == category_for_mcc("0711")

    def test_surrounding_whitespace_tolerated(self):
        assert category_for_mcc("  5411  ") == "Groceries"

    def test_accepts_integer_input(self):
        assert category_for_mcc(5411) == "Groceries"


class TestObservedCodes:
    """The codes the connected accounts actually send."""

    @pytest.mark.parametrize(
        "code,expected",
        [
            ("5411", "Groceries"),   # Food Lion
            ("5812", "Dining"),      # restaurants
            ("5814", "Dining"),      # fast food
            ("5813", "Dining"),      # Arcana Bar
            ("5811", "Dining"),      # caterers
            ("5200", "Shopping"),    # home supply warehouse
            ("5331", "Shopping"),    # variety stores
            ("5999", "Shopping"),    # misc retail catch-all
            ("5994", "Shopping"),    # newsstands
            ("5921", "Groceries"),   # package/liquor store
            ("5912", "Health"),      # pharmacy
            ("5541", "Gas"),         # service stations
            ("5542", "Gas"),         # automated fuel dispensers
        ],
    )
    def test_live_codes_resolve(self, code, expected):
        assert category_for_mcc(code) == expected


class TestBrandRanges:
    """Airlines, car rental and lodging get one code per brand."""

    @pytest.mark.parametrize("code", ["3000", "3299", "3300", "3499", "3500", "3999"])
    def test_ranges_resolve_to_travel(self, code):
        assert category_for_mcc(code) == "Travel"

    def test_just_below_range_is_not_travel(self):
        assert category_for_mcc("2999") is None

    def test_just_above_range_is_not_travel(self):
        # 4000 is unassigned; the explicit 4xxx transport/travel codes are
        # listed individually rather than swept in by a range.
        assert category_for_mcc("4000") is None

    def test_explicit_entry_wins_over_range(self):
        # No overlap today, but the lookup checks the table first by design.
        assert category_for_mcc("4511") == "Travel"
