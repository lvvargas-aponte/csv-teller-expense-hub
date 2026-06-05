"""Unit tests for category_normalizer.normalize.

Covers every distinct category string observed in production data
(survey from 2026-05-28, 51 distinct labels across 313 transactions)
plus a handful of edge cases.
"""
import pytest

from category_normalizer import NORMALIZATION_MAP, normalize


# ---------------------------------------------------------------------------
# Approved explicit mappings — these are the "before → after" pairs the user
# signed off on. If any of these change, the live ingest path will diverge
# from the one-shot backfill.
# ---------------------------------------------------------------------------

_EXPLICIT_MAPPINGS = [
    # Case fixes
    ("groceries", "Groceries"),
    ("shopping", "Shopping"),
    ("utilities", "Utilities"),
    ("general", "General"),
    ("service", "Service"),
    ("home maintenance", "Home Maintenance"),
    # Typo
    ("Car Maintenace", "Car Maintenance"),
    # Spacing / form
    ("FoodDeliveryService", "Food Delivery"),
    ("Travel/ Entertainment", "Travel"),
    ("Drinking", "Drinks"),
    ("SelfHelp", "Self Help"),
    # Synonym merges
    ("fuel", "Gas"),
    ("Restaurants", "Dining"),
    ("Supermarkets", "Groceries"),
    ("Merchandise", "Shopping"),
]


@pytest.mark.parametrize("raw,expected", _EXPLICIT_MAPPINGS)
def test_explicit_mappings(raw, expected):
    assert normalize(raw) == expected


# ---------------------------------------------------------------------------
# Already-canonical labels pass through unchanged.
# ---------------------------------------------------------------------------

_CANONICAL_PASSTHROUGH = [
    "CC Payment", "Dining", "Drinks", "Subscriptions", "Payroll", "Interest",
    "Zelle To", "Zelle From", "Gifts and Donations", "Travel", "Savings",
    "Mortgage", "Parking", "Furniture", "Payments and Credits",
    "Car Insurance", "Entertainment", "Gym Fees", "Eastern Medicine",
    "Coffee", "Health Care", "Pharmacy", "Car Payment", "Hotel", "Gas",
    "Check Deposit", "ATM Withdraw", "Fees", "Tax Service", "HOA",
    "Souvenir", "Self Care", "Self Help", "Insurance", "Groceries",
    "Shopping", "Utilities",
]


@pytest.mark.parametrize("label", _CANONICAL_PASSTHROUGH)
def test_canonical_labels_unchanged(label):
    assert normalize(label) == label


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEmptyAndNone:
    def test_none_returns_none(self):
        assert normalize(None) is None

    def test_empty_string_returns_none(self):
        assert normalize("") is None

    def test_whitespace_only_returns_none(self):
        assert normalize("   ") is None

    def test_surrounding_whitespace_stripped(self):
        assert normalize("  groceries  ") == "Groceries"


class TestFallbackBehavior:
    def test_unknown_lowercase_titlecased(self):
        # A label we haven't mapped yet shouldn't be dropped — titlecase so
        # the user can spot it in the UI and decide whether to add it.
        assert normalize("crypto") == "Crypto"

    def test_unknown_uppercase_word_titlecased(self):
        assert normalize("CRYPTO") == "Crypto"

    def test_short_uppercase_acronyms_preserved(self):
        # HOA, ATM, CC etc. should stay uppercase rather than becoming "Hoa".
        assert normalize("HOA") == "HOA"
        assert normalize("ATM Withdraw") == "ATM Withdraw"
        assert normalize("CC Payment") == "CC Payment"

    def test_multi_word_unknown(self):
        assert normalize("nightclub cover") == "Nightclub Cover"


class TestIdempotency:
    @pytest.mark.parametrize("raw,_expected", _EXPLICIT_MAPPINGS)
    def test_explicit_mappings_idempotent(self, raw, _expected):
        once = normalize(raw)
        twice = normalize(once)
        assert once == twice

    @pytest.mark.parametrize("label", _CANONICAL_PASSTHROUGH)
    def test_canonical_idempotent(self, label):
        assert normalize(normalize(label)) == normalize(label)

    def test_fallback_idempotent(self):
        assert normalize(normalize("crypto")) == normalize("crypto")


class TestMapValuesAreCanonical:
    """Every right-hand side in NORMALIZATION_MAP must normalize to itself.

    Otherwise a second pass over the data would keep changing rows.
    """
    @pytest.mark.parametrize("canonical", sorted(set(NORMALIZATION_MAP.values())))
    def test_map_values_are_fixed_points(self, canonical):
        assert normalize(canonical) == canonical
